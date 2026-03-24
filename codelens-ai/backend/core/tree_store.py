import json
import os
import time
from pathlib import Path
from typing import Optional

from backend.config import TREE_STORAGE_PATH
from backend.models.schemas import TreeNode


def _tree_dir() -> Path:
    p = Path(TREE_STORAGE_PATH)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _tree_path(repo_name: str, commit_hash: str) -> Path:
    return _tree_dir() / f"{repo_name}_{commit_hash}.json"


def save_tree(tree: TreeNode, repo_name: str, commit_hash: str) -> str:
    """Serialize and save the tree to a JSON file. Returns the file path."""
    path = _tree_path(repo_name, commit_hash)
    data = tree.model_dump()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(path)


def load_tree(repo_name: str, commit_hash: str) -> Optional[TreeNode]:
    """Load a tree from disk. Returns None if not found."""
    path = _tree_path(repo_name, commit_hash)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return TreeNode(**data)


def check_cache(repo_name: str, commit_hash: str) -> bool:
    """Check whether a cached tree exists for this repo+commit."""
    return _tree_path(repo_name, commit_hash).exists()


def list_cached_repos() -> list[dict]:
    """List all cached tree files with metadata."""
    results = []
    for f in _tree_dir().glob("*.json"):
        parts = f.stem.rsplit("_", 1)
        stat = f.stat()
        results.append({
            "repo_name": parts[0] if len(parts) == 2 else f.stem,
            "commit_hash": parts[1] if len(parts) == 2 else "unknown",
            "file_size": stat.st_size,
            "created_at": stat.st_ctime,
        })
    return results


def delete_tree(repo_name: str, commit_hash: str) -> bool:
    """Delete a cached tree file. Returns True if deleted."""
    path = _tree_path(repo_name, commit_hash)
    if path.exists():
        path.unlink()
        return True
    return False


def cleanup_old_trees(max_age_days: int = 7) -> int:
    """Delete tree files older than max_age_days. Returns count deleted."""
    cutoff = time.time() - (max_age_days * 86400)
    count = 0
    for f in _tree_dir().glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            count += 1
    return count
