import asyncio
import logging
import threading

from backend.core.cloner import cleanup_repo, clone_repo, _repo_name_from_url
from backend.core.parser import count_nodes, parse_repo
from backend.core.summarizer import summarize_tree
from backend.core.tree_store import check_cache, save_tree, _tree_path
from backend.models.database import get_repo, update_repo_status


class IndexingCancelled(Exception):
    """Raised when the repo has been deleted mid-indexing."""
    pass


def _check_cancelled(repo_id: str) -> None:
    """Abort if the repo was deleted (user clicked stop)."""
    if get_repo(repo_id) is None:
        raise IndexingCancelled(f"Repo {repo_id} was deleted -- aborting")

logger = logging.getLogger(__name__)


def _redis_available() -> bool:
    """Check if Redis is reachable."""
    try:
        from redis import Redis
        from backend.config import REDIS_URL
        conn = Redis.from_url(REDIS_URL, socket_connect_timeout=1)
        conn.ping()
        conn.close()
        return True
    except Exception:
        return False


def _get_queue():
    """Lazily import RQ and create the queue (avoids import errors on Windows)."""
    from redis import Redis
    from rq import Queue
    from backend.config import REDIS_URL

    conn = Redis.from_url(REDIS_URL)
    return Queue("codelens", connection=conn)


def enqueue_indexing(repo_id: str, repo_url: str) -> str:
    """Enqueue via Redis/RQ if available, otherwise run in a background thread."""
    if _redis_available():
        try:
            q = _get_queue()
            job = q.enqueue(
                "backend.workers.indexing_worker.process_indexing_job",
                repo_id,
                repo_url,
                job_timeout="10m",
                result_ttl=0,
            )
            return job.id
        except Exception:
            pass

    # Fallback: run in a background thread (works on Windows without Redis)
    logger.info("Redis not available -- running indexing in background thread")
    t = threading.Thread(
        target=process_indexing_job,
        args=(repo_id, repo_url),
        daemon=True,
    )
    t.start()
    return "thread-fallback"


def process_indexing_job(repo_id: str, repo_url: str) -> None:
    local_path = None
    try:
        # Step 1: Clone
        update_repo_status(repo_id, "cloning")
        local_path, commit_hash = clone_repo(repo_url)
        update_repo_status(repo_id, "cloning", commit_hash=commit_hash)

        _check_cancelled(repo_id)

        # Check cache
        repo_name = _repo_name_from_url(repo_url)
        if check_cache(repo_name, commit_hash):
            tree_path = str(_tree_path(repo_name, commit_hash))
            update_repo_status(repo_id, "ready", tree_path=tree_path, progress=100)
            cleanup_repo(local_path)
            return

        # Step 2: Parse
        update_repo_status(repo_id, "parsing")
        tree = parse_repo(local_path)
        total_nodes = count_nodes(tree)
        update_repo_status(repo_id, "parsing", total_nodes=total_nodes)

        _check_cancelled(repo_id)

        # Step 3: Summarize
        update_repo_status(repo_id, "summarizing", progress=0)

        def on_progress(current, total):
            pct = int((current / total) * 100)
            # Check for cancellation every 5 nodes
            if current % 5 == 0:
                _check_cancelled(repo_id)
            update_repo_status(repo_id, "summarizing", progress=pct)

        tree = asyncio.run(summarize_tree(tree, on_progress=on_progress))

        _check_cancelled(repo_id)

        # Step 4: Save
        tree_path = save_tree(tree, repo_name, commit_hash)
        update_repo_status(repo_id, "ready", tree_path=tree_path, progress=100)

        # Cleanup
        cleanup_repo(local_path)

    except IndexingCancelled:
        logger.info("Indexing cancelled for repo %s", repo_id)
        if local_path:
            try:
                cleanup_repo(local_path)
            except Exception:
                pass

    except Exception as e:
        update_repo_status(repo_id, "failed", error_message=str(e))
        if local_path:
            try:
                cleanup_repo(local_path)
            except Exception:
                pass
