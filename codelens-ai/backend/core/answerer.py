import asyncio
import time
from typing import AsyncGenerator, Callable, List, Optional

from backend.config import GEMINI_MODEL
from backend.core.summarizer import _get_client  # reuse singleton client
from backend.models.schemas import ThinkingStep, TreeNode


def _build_answer_prompt(query: str, nodes: List[TreeNode], repo_name: str) -> str:
    # Group nodes by file path
    by_file: dict[str, list[TreeNode]] = {}
    for n in nodes:
        file_path = n.path.rsplit(":", 1)[0] if ":" in n.path else n.path
        by_file.setdefault(file_path, []).append(n)

    context_parts = []
    for file_path, file_nodes in by_file.items():
        for node in file_nodes:
            lang = node.language or ""
            summary = node.summary.summary if node.summary else ""
            deps = ", ".join(node.summary.dependencies) if node.summary else ""
            snippet = node.code_snippet or ""
            context_parts.append(
                f"### {node.path}\n"
                f"**{node.name}** ({node.type})\n"
                f"Summary: {summary}\n"
                f"Dependencies: {deps}\n\n"
                f"```{lang}\n{snippet}\n```\n"
            )

    context = "\n---\n\n".join(context_parts)

    return f"""You are CodeLens, an expert code assistant helping users understand a GitHub repository called "{repo_name}".

Answer the user's question using ONLY the provided code context. Be accurate and specific.

## User Question
{query}

## Code Context
{context}

## Instructions
- Reference specific files and function names in your answer using `backtick` formatting
- Include short code snippets where they help explain the answer
- Structure your answer clearly with paragraphs (not bullet points unless listing items)
- If you can trace a flow across files (e.g., request -> middleware -> handler -> database), describe it step by step
- If the context doesn't fully answer the question, state what you CAN infer and mention what additional files might help
- Keep the answer concise but thorough -- aim for 150-400 words
- Do NOT make up code that isn't in the context
- Do NOT hallucinate file names, function names, or behaviors not shown in the context"""


def get_source_references(nodes: List[TreeNode]) -> List[dict]:
    """Return source reference metadata for each selected node."""
    refs = []
    seen = set()
    for n in nodes:
        file_path = n.path.rsplit(":", 1)[0] if ":" in n.path else n.path
        key = (file_path, n.name)
        if key not in seen:
            seen.add(key)
            refs.append({
                "file_path": file_path,
                "node_name": n.name,
                "node_type": n.type,
            })
    return refs


async def generate_answer(
    query: str,
    selected_nodes: List[TreeNode],
    repo_name: str,
    on_thinking: Optional[Callable[[ThinkingStep], None]] = None,
) -> AsyncGenerator[str, None]:
    """Stream an answer from Gemini based on selected code context."""

    if not selected_nodes:
        yield (
            "I couldn't find relevant code sections for your question. "
            "Try rephrasing or ask about a different part of the codebase."
        )
        return

    if on_thinking:
        on_thinking(ThinkingStep(
            step_type="generating",
            message=f"Generating answer from {len(selected_nodes)} relevant code sections...",
            timestamp=time.time(),
        ))

    prompt = _build_answer_prompt(query, selected_nodes, repo_name)
    client = _get_client()

    try:
        from google import genai as _genai

        # Run the entire streaming call + iteration inside a thread so we
        # never block the async event loop.  Chunks are fed back via an
        # asyncio.Queue.
        q: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _stream_in_thread() -> None:
            try:
                stream = client.models.generate_content_stream(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=_genai.types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=2000,
                    ),
                )
                for chunk in stream:
                    if chunk.text:
                        loop.call_soon_threadsafe(q.put_nowait, chunk.text)
            except Exception as exc:
                loop.call_soon_threadsafe(
                    q.put_nowait,
                    f"\n\n**Error:** {exc}",
                )
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        loop.run_in_executor(None, _stream_in_thread)

        while True:
            chunk = await q.get()
            if chunk is None:
                break
            yield chunk
    except Exception:
        yield "I encountered an error generating the answer. Please try again."
