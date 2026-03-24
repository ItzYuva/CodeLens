import time
from typing import AsyncGenerator, Callable, List, Optional

from backend.core.answerer import generate_answer, get_source_references
from backend.core.bm25_filter import BM25Filter
from backend.core.traverser import traverse_tree
from backend.core.tree_store import load_tree
from backend.models.schemas import ThinkingStep, TreeNode


async def run_query(
    query: str,
    repo_name: str,
    commit_hash: str,
    on_thinking: Optional[Callable[[ThinkingStep], None]] = None,
) -> AsyncGenerator[dict, None]:
    """Run the full query pipeline, yielding thinking steps and answer chunks."""

    # Collect thinking steps so they can be forwarded via the callback AND yielded
    def emit(step: ThinkingStep):
        if on_thinking:
            on_thinking(step)

    # 1. Load tree
    emit(ThinkingStep(
        step_type="searching",
        message="Loading codebase index...",
        timestamp=time.time(),
    ))
    yield {"type": "thinking", "step": ThinkingStep(
        step_type="searching",
        message="Loading codebase index...",
        timestamp=time.time(),
    )}

    tree = load_tree(repo_name, commit_hash)
    if tree is None:
        yield {"type": "error", "message": f"No indexed tree found for {repo_name}@{commit_hash}. Please index the repository first."}
        yield {"type": "done"}
        return

    # 2. BM25 pre-filter
    bm25 = BM25Filter(tree)
    bm25_candidates: Optional[List[TreeNode]] = None

    if not bm25.should_skip():
        thinking_steps: list[ThinkingStep] = []

        def collect_thinking(step: ThinkingStep):
            thinking_steps.append(step)
            emit(step)

        bm25_candidates = bm25.filter(query, top_k=10, on_thinking=collect_thinking)

        for step in thinking_steps:
            yield {"type": "thinking", "step": step}
    else:
        step = ThinkingStep(
            step_type="searching",
            message=f"Small repository ({len(bm25.file_nodes)} files) -- scanning all files...",
            timestamp=time.time(),
        )
        emit(step)
        yield {"type": "thinking", "step": step}

    # 3. Lazy tree traversal
    traversal_steps: list[ThinkingStep] = []

    def collect_traversal(step: ThinkingStep):
        traversal_steps.append(step)
        emit(step)

    try:
        selected_nodes = await traverse_tree(
            query=query,
            tree=tree,
            bm25_candidates=bm25_candidates,
            on_thinking=collect_traversal,
        )
    except Exception as e:
        # Fallback: try answering with top-level summaries
        step = ThinkingStep(
            step_type="error",
            message=f"Tree traversal failed ({e}), using top-level summaries as fallback...",
            timestamp=time.time(),
        )
        emit(step)
        yield {"type": "thinking", "step": step}

        selected_nodes = [c for c in tree.children if c.type == "file"][:5]
        if not selected_nodes:
            for d in tree.children:
                if d.type == "directory":
                    selected_nodes.extend(c for c in d.children if c.type == "file")
                    if len(selected_nodes) >= 5:
                        break
            selected_nodes = selected_nodes[:5]

    for step in traversal_steps:
        yield {"type": "thinking", "step": step}

    # 4. Generate streamed answer
    answer_steps: list[ThinkingStep] = []

    def collect_answer(step: ThinkingStep):
        answer_steps.append(step)
        emit(step)

    async for chunk in generate_answer(
        query=query,
        selected_nodes=selected_nodes,
        repo_name=repo_name,
        on_thinking=collect_answer,
    ):
        # Yield any thinking steps that came before the first chunk
        while answer_steps:
            yield {"type": "thinking", "step": answer_steps.pop(0)}
        yield {"type": "answer_chunk", "content": chunk}

    # 5. Source references
    sources = get_source_references(selected_nodes)
    yield {"type": "sources", "sources": sources}

    # 6. Done
    yield {"type": "done"}
