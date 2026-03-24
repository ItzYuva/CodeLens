import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from backend.config import DATABASE_PATH
from backend.models.schemas import RepoMetadata


def _get_conn() -> sqlite3.Connection:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db() -> None:
    conn = _get_conn()
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repos (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            commit_hash TEXT,
            status TEXT DEFAULT 'queued',
            progress INTEGER DEFAULT 0,
            total_nodes INTEGER DEFAULT 0,
            error_message TEXT,
            tree_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _row_to_metadata(row: sqlite3.Row) -> RepoMetadata:
    return RepoMetadata(
        repo_id=row["id"],
        url=row["url"],
        name=row["name"],
        commit_hash=row["commit_hash"] or "",
        status=row["status"],
        progress=row["progress"],
        total_nodes=row["total_nodes"],
        error_message=row["error_message"],
        tree_path=row["tree_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_repo(url: str, name: str) -> RepoMetadata:
    repo_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO repos (id, url, name, status, created_at, updated_at) VALUES (?, ?, ?, 'queued', ?, ?)",
        (repo_id, url, name, now, now),
    )
    conn.commit()
    conn.close()
    return RepoMetadata(repo_id=repo_id, url=url, name=name, commit_hash="", created_at=now, updated_at=now)


def get_repo(repo_id: str) -> Optional[RepoMetadata]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_metadata(row)


def get_repo_by_url(url: str) -> Optional[RepoMetadata]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM repos WHERE url = ?", (url,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_metadata(row)


def update_repo_status(repo_id: str, status: str, **kwargs) -> None:
    now = datetime.now(timezone.utc).isoformat()
    fields = ["status = ?", "updated_at = ?"]
    values: list = [status, now]

    for key in ("progress", "total_nodes", "commit_hash", "tree_path", "error_message"):
        if key in kwargs:
            fields.append(f"{key} = ?")
            values.append(kwargs[key])

    values.append(repo_id)
    conn = _get_conn()
    conn.execute(f"UPDATE repos SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def list_repos(limit: int = 20) -> List[RepoMetadata]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM repos ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [_row_to_metadata(r) for r in rows]


def delete_repo(repo_id: str) -> bool:
    repo = get_repo(repo_id)
    if repo is None:
        return False

    # Delete tree file if it exists
    if repo.tree_path:
        path = Path(repo.tree_path)
        if path.exists():
            path.unlink()

    conn = _get_conn()
    conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
    conn.commit()
    conn.close()
    return True
