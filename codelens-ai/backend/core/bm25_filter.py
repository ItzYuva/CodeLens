import re
import time
from typing import Callable, List, Optional

from rank_bm25 import BM25Okapi

from backend.models.schemas import ThinkingStep, TreeNode


def _tokenize(text: str) -> List[str]:
    """Tokenize text, splitting camelCase and snake_case."""
    # Split camelCase: "getUserData" -> "get User Data"
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # Split snake_case and other punctuation
    tokens = re.split(r"[_\s\-./,;:(){}[\]\"']+", text.lower())
    return [t for t in tokens if t and len(t) > 1]


def _extract_file_nodes(node: TreeNode) -> List[TreeNode]:
    """Flatten the tree to get all file-level nodes."""
    files = []
    if node.type == "file":
        files.append(node)
    for child in node.children:
        files.extend(_extract_file_nodes(child))
    return files


def _build_corpus_entry(node: TreeNode) -> str:
    """Build a searchable text string from a file node's metadata."""
    parts = [node.name, node.path]
    if node.summary:
        parts.append(node.summary.summary)
        parts.extend(node.summary.exports)
        parts.extend(node.summary.key_signatures)
        parts.extend(node.summary.dependencies)
    if node.imports:
        parts.extend(node.imports)
    for child in node.children:
        parts.append(child.name)
        if child.summary:
            parts.append(child.summary.summary)
    return " ".join(parts)


class BM25Filter:
    def __init__(self, tree: TreeNode):
        self.file_nodes = _extract_file_nodes(tree)
        corpus_texts = [_build_corpus_entry(n) for n in self.file_nodes]
        self.tokenized_corpus = [_tokenize(t) for t in corpus_texts]
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self.bm25 = None

    def should_skip(self) -> bool:
        return len(self.file_nodes) < 30

    def filter(
        self,
        query: str,
        top_k: int = 10,
        on_thinking: Optional[Callable[[ThinkingStep], None]] = None,
    ) -> List[TreeNode]:
        if not self.file_nodes or self.bm25 is None:
            return self.file_nodes

        if on_thinking:
            on_thinking(ThinkingStep(
                step_type="searching",
                message=f"Searching across {len(self.file_nodes)} files using keyword matching...",
                timestamp=time.time(),
            ))

        query_tokens = _tokenize(query)
        scores = self.bm25.get_scores(query_tokens)

        scored = sorted(
            zip(self.file_nodes, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        results = [node for node, score in scored[:top_k] if score > 0]

        # If no results had positive scores, return top_k anyway
        if not results:
            results = [node for node, _ in scored[:top_k]]

        if on_thinking:
            on_thinking(ThinkingStep(
                step_type="filtering",
                message=f"Found {len(results)} candidate files -- narrowing down...",
                timestamp=time.time(),
            ))

        return results
