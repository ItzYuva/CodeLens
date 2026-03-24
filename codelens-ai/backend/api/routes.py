from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.cloner import validate_github_url, _clean_url, _repo_name_from_url
from backend.models.database import (
    create_repo,
    delete_repo,
    get_repo,
    get_repo_by_url,
    list_repos,
    update_repo_status,
)
from backend.workers.indexing_worker import enqueue_indexing

router = APIRouter(prefix="/api")

# If a repo hasn't been updated in this many seconds while still
# in an in-progress state, consider it stale / dead and re-queue.
_STALE_TIMEOUT_SECONDS = 300  # 5 minutes


def _is_stale(repo) -> bool:
    """Return True if the repo's indexing job appears to have died."""
    if not repo.updated_at:
        return True
    try:
        # Handle both ISO format strings and datetime objects
        updated = repo.updated_at
        if isinstance(updated, str):
            # Strip trailing 'Z' and parse
            updated = updated.rstrip("Z")
            updated = datetime.fromisoformat(updated).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        return age > _STALE_TIMEOUT_SECONDS
    except Exception:
        return True  # if we can't parse the date, assume stale


class IndexRequest(BaseModel):
    repo_url: str


class IndexResponse(BaseModel):
    repo_id: str
    name: str
    status: str
    message: str


@router.post("/index", response_model=IndexResponse)
def index_repo(request: IndexRequest):
    url = _clean_url(request.repo_url)

    if not validate_github_url(request.repo_url):
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")

    repo_name = _repo_name_from_url(url)

    # Check if already exists
    existing = get_repo_by_url(url)
    if existing:
        if existing.status == "ready":
            return IndexResponse(
                repo_id=existing.repo_id,
                name=existing.name,
                status="ready",
                message="Repository already indexed",
            )
        if existing.status in ("queued", "cloning", "parsing", "summarizing"):
            # Check if the job is stale (thread died, no updates for 5 min)
            if _is_stale(existing):
                # Dead job — reset and re-queue
                update_repo_status(
                    existing.repo_id, "queued",
                    error_message=None, progress=0, total_nodes=0,
                )
                try:
                    enqueue_indexing(existing.repo_id, url)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to enqueue job: {e}")
                return IndexResponse(
                    repo_id=existing.repo_id,
                    name=existing.name,
                    status="queued",
                    message="Previous indexing job was stale — re-queued",
                )
            return IndexResponse(
                repo_id=existing.repo_id,
                name=existing.name,
                status=existing.status,
                message="Repository is currently being indexed",
            )
        if existing.status == "failed":
            # Reset and re-queue
            update_repo_status(existing.repo_id, "queued", error_message=None, progress=0)
            try:
                enqueue_indexing(existing.repo_id, url)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to enqueue job: {e}")
            return IndexResponse(
                repo_id=existing.repo_id,
                name=existing.name,
                status="queued",
                message="Re-queued failed repository for indexing",
            )

    # Create new entry
    repo = create_repo(url, repo_name)
    try:
        enqueue_indexing(repo.repo_id, url)
    except Exception as e:
        update_repo_status(repo.repo_id, "failed", error_message=f"Failed to enqueue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enqueue job: {e}")

    return IndexResponse(
        repo_id=repo.repo_id,
        name=repo.name,
        status="queued",
        message="Repository queued for indexing",
    )


@router.get("/status/{repo_id}")
def repo_status(repo_id: str):
    repo = get_repo(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {
        "repo_id": repo.repo_id,
        "url": repo.url,
        "name": repo.name,
        "status": repo.status,
        "progress": repo.progress,
        "total_nodes": repo.total_nodes,
        "error_message": repo.error_message,
        "created_at": str(repo.created_at),
        "updated_at": str(repo.updated_at),
    }


@router.get("/repos")
def get_repos(limit: int = 20):
    repos = list_repos(limit=limit)
    return [
        {
            "repo_id": r.repo_id,
            "url": r.url,
            "name": r.name,
            "status": r.status,
            "progress": r.progress,
            "created_at": str(r.created_at),
        }
        for r in repos
    ]


@router.delete("/repos/{repo_id}")
def remove_repo(repo_id: str):
    deleted = delete_repo(repo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {"deleted": True}
