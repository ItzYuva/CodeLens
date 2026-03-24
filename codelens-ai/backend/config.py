import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
REPO_CLONE_PATH: str = os.getenv("REPO_CLONE_PATH", str(BASE_DIR / "data" / "repos"))
TREE_STORAGE_PATH: str = os.getenv("TREE_STORAGE_PATH", str(BASE_DIR / "data" / "trees"))
MAX_REPO_SIZE_MB: int = int(os.getenv("MAX_REPO_SIZE_MB", "100"))
MAX_FILES_PER_REPO: int = int(os.getenv("MAX_FILES_PER_REPO", "500"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "codelens.db"))
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
