import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from backend.config import REPO_CLONE_PATH


def validate_github_url(url: str) -> bool:
    """Validate that the URL is a proper GitHub repository URL."""
    pattern = r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$"
    cleaned = url.rstrip("/").removesuffix(".git")
    return bool(re.match(pattern, cleaned))


def _clean_url(url: str) -> str:
    return url.rstrip("/").removesuffix(".git")


def _repo_name_from_url(url: str) -> str:
    return _clean_url(url).rstrip("/").split("/")[-1]


def clone_repo(url: str) -> tuple[str, str]:
    """Clone a GitHub repo (shallow) and return (local_path, commit_hash)."""
    if not validate_github_url(url):
        raise ValueError(f"Invalid GitHub URL: {url}")

    cleaned_url = _clean_url(url)
    repo_name = _repo_name_from_url(url)
    short_id = uuid4().hex[:8]
    target_path = Path(REPO_CLONE_PATH) / f"{repo_name}_{short_id}"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", cleaned_url, str(target_path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(target_path, ignore_errors=True)
        raise TimeoutError(f"Cloning {cleaned_url} timed out after 120 seconds")
    except subprocess.CalledProcessError as e:
        shutil.rmtree(target_path, ignore_errors=True)
        stderr = e.stderr.strip()
        if "Repository not found" in stderr or "Could not read from remote" in stderr:
            raise PermissionError(f"Repository not accessible: {cleaned_url}")
        raise RuntimeError(f"Git clone failed: {stderr}")

    # Get commit hash
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(target_path),
    )
    commit_hash = result.stdout.strip()

    return str(target_path), commit_hash


def cleanup_repo(local_path: str) -> None:
    """Delete a cloned repo directory."""
    path = Path(local_path)
    if path.exists():
        shutil.rmtree(path)
