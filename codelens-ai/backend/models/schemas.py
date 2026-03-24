from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class NodeSummary(BaseModel):
    summary: str
    exports: List[str] = []
    dependencies: List[str] = []
    key_signatures: List[str] = []


class TreeNode(BaseModel):
    name: str
    type: str  # "directory", "file", "class", "function", "method"
    language: Optional[str] = None  # "python", "javascript", "typescript"
    path: str  # relative path from repo root
    imports: Optional[List[str]] = None
    code_snippet: Optional[str] = None
    params: Optional[List[str]] = None
    children: List[TreeNode] = []
    summary: Optional[NodeSummary] = None


STEP_PREFIXES = {
    "searching": "[SEARCH]",
    "filtering": "[FILTER]",
    "exploring": "[EXPLORE]",
    "reading": "[READ]",
    "generating": "[GENERATE]",
    "error": "[ERROR]",
}


class ThinkingStep(BaseModel):
    step_type: str  # "searching", "filtering", "exploring", "reading", "generating", "error"
    message: str
    timestamp: float

    @property
    def prefix(self) -> str:
        return STEP_PREFIXES.get(self.step_type, "[INFO]")

    @property
    def display(self) -> str:
        return f"{self.prefix} {self.message}"


class RepoMetadata(BaseModel):
    repo_id: str = Field(default_factory=lambda: str(uuid4()))
    url: str
    name: str
    commit_hash: str
    status: str = "queued"  # queued/cloning/parsing/summarizing/ready/failed
    progress: int = 0
    total_nodes: int = 0
    error_message: Optional[str] = None
    tree_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
