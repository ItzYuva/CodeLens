import asyncio
import json
import re
from typing import Callable, List, Optional

from google import genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL
from backend.models.schemas import NodeSummary, TreeNode

# ── Singleton Gemini client ──────────────────────────────────────────
_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from Gemini responses."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


# ── Trivial-node auto-summary (no API call) ──────────────────────────

_TRIVIAL_LINE_THRESHOLD = 15  # functions ≤ this many lines skip the API


def _can_auto_summarize(node: TreeNode) -> bool:
    """Return True if the node is small enough to summarize without an API call."""
    if node.type not in ("function", "method"):
        return False
    snippet = node.code_snippet or ""
    return snippet.count("\n") + 1 <= _TRIVIAL_LINE_THRESHOLD


def _auto_summary(node: TreeNode) -> NodeSummary:
    """Build a summary from the code itself — no LLM needed."""
    params = ", ".join(node.params) if node.params else ""
    sig = f"{node.name}({params})"
    snippet = (node.code_snippet or "").strip()
    # Grab the first meaningful line as a one-liner description
    first_line = ""
    for line in snippet.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//", "/*", "*", "def ", "function ")):
            first_line = stripped
            break
    desc = first_line if first_line else f"A small {node.type} named {node.name}."
    return NodeSummary(
        summary=f"{node.type.title()} `{node.name}`. {desc}",
        exports=[node.name],
        dependencies=[],
        key_signatures=[sig],
    )


# ── Prompt builders ──────────────────────────────────────────────────

def _build_prompt_function(node: TreeNode) -> str:
    params = ", ".join(node.params) if node.params else ""
    lang = node.language or "code"
    return f"""You are a code documentation expert. Summarize this {lang} function concisely.

Name: {node.name}
Parameters: {params}
Code:
```{lang}
{node.code_snippet or ""}
```

Respond ONLY with valid JSON (no markdown, no backticks):
{{"summary": "2-4 sentence description of what this function does", "exports": ["symbols it exposes"], "dependencies": ["external modules/functions it calls"], "key_signatures": ["{node.name}({params}) description"]}}"""


def _build_prompt_class(node: TreeNode) -> str:
    lang = node.language or "code"
    methods_text = ""
    for child in node.children:
        child_summary = child.summary.summary if child.summary else "No summary available"
        methods_text += f"- {child.name}: {child_summary}\n"

    return f"""You are a code documentation expert. Summarize this {lang} class concisely.

Class: {node.name}
Methods and their summaries:
{methods_text}

Respond ONLY with valid JSON (no markdown, no backticks):
{{"summary": "2-4 sentence description of this class's purpose and responsibilities", "exports": ["public methods and properties"], "dependencies": ["external things this class uses"], "key_signatures": ["important method signatures"]}}"""


def _build_prompt_file(node: TreeNode) -> str:
    lang = node.language or "code"
    imports_text = ", ".join(node.imports) if node.imports else "None"
    contents_text = ""
    for child in node.children:
        child_summary = child.summary.summary if child.summary else "No summary available"
        contents_text += f"- {child.name} ({child.type}): {child_summary}\n"

    return f"""You are a code documentation expert. Summarize this {lang} file concisely.

File: {node.name}
Imports: {imports_text}
Contents:
{contents_text}

Respond ONLY with valid JSON (no markdown, no backticks):
{{"summary": "2-4 sentence description of this file's purpose", "exports": ["symbols exported from this file"], "dependencies": ["external packages this file imports"], "key_signatures": ["key function/class signatures"]}}"""


def _build_prompt_directory(node: TreeNode) -> str:
    contents_text = ""
    for child in node.children:
        child_summary = child.summary.summary if child.summary else "No summary available"
        contents_text += f"- {child.name} ({child.type}): {child_summary}\n"

    return f"""You are a code documentation expert. Summarize this directory in a codebase.

Directory: {node.name}
Contains:
{contents_text}

Respond ONLY with valid JSON (no markdown, no backticks):
{{"summary": "2-4 sentence description of what this directory/module handles", "exports": ["key modules/symbols available from this directory"], "dependencies": ["external packages used across files in this directory"], "key_signatures": ["most important function/class signatures"]}}"""


def _build_prompt(node: TreeNode) -> str:
    if node.type in ("function", "method"):
        return _build_prompt_function(node)
    elif node.type == "class":
        return _build_prompt_class(node)
    elif node.type == "file":
        return _build_prompt_file(node)
    elif node.type == "directory":
        return _build_prompt_directory(node)
    return _build_prompt_file(node)


def _fallback_summary(node: TreeNode) -> NodeSummary:
    return NodeSummary(
        summary=f"{node.type.title()} '{node.name}' in the codebase.",
        exports=[node.name],
        dependencies=[],
        key_signatures=[],
    )


# ── Batch prompt for multiple leaf nodes at once ─────────────────────

_BATCH_SIZE = 20  # summarize up to 20 leaf nodes per API call


def _build_batch_prompt(nodes: List[TreeNode]) -> str:
    entries = []
    for i, node in enumerate(nodes):
        params = ", ".join(node.params) if node.params else ""
        lang = node.language or "code"
        snippet = node.code_snippet or ""
        entries.append(
            f"### {i+1}. {node.name} ({node.type}, {lang})\n"
            f"Parameters: {params}\n"
            f"```{lang}\n{snippet}\n```"
        )

    items_json = ", ".join(
        f'{{"name": "{n.name}", "summary": "...", "exports": [...], "dependencies": [...], "key_signatures": [...]}}'
        for n in nodes[:2]
    )

    return f"""You are a code documentation expert. Summarize each of these code elements concisely.

{chr(10).join(entries)}

Respond ONLY with a JSON array (no markdown, no backticks). One object per element, in the same order:
[{items_json}, ...]

Each object must have: "name" (string), "summary" (string, 1-2 sentences), "exports" (list), "dependencies" (list), "key_signatures" (list)."""


async def _summarize_batch(nodes: List[TreeNode]) -> List[NodeSummary]:
    """Summarize multiple leaf nodes in a single API call."""
    prompt = _build_batch_prompt(nodes)
    try:
        raw = await call_gemini(prompt)
        cleaned = _strip_code_fences(raw)
        data = json.loads(cleaned)
        if not isinstance(data, list) or len(data) != len(nodes):
            raise ValueError("Batch response mismatch")
        return [NodeSummary(**item) for item in data]
    except Exception:
        # Fall back to individual fallback summaries
        return [_fallback_summary(n) for n in nodes]


# ── Core API call ────────────────────────────────────────────────────

async def call_gemini(prompt: str) -> str:
    """Call Gemini Flash API with retries (uses singleton client)."""
    client = _get_client()
    last_error = None

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=500,
                ),
            )
            return response.text
        except Exception as e:
            last_error = e
            if attempt < 2:
                await asyncio.sleep(0.5 * (2 ** attempt))

    raise last_error


async def summarize_node(node: TreeNode) -> NodeSummary:
    """Summarize a single node using Gemini."""
    if _can_auto_summarize(node):
        return _auto_summary(node)
    prompt = _build_prompt(node)
    try:
        raw = await call_gemini(prompt)
        cleaned = _strip_code_fences(raw)
        data = json.loads(cleaned)
        return NodeSummary(**data)
    except Exception:
        return _fallback_summary(node)


async def summarize_tree(
    tree: TreeNode,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> TreeNode:
    """Traverse the tree bottom-up and summarize every node.

    Uses batching for leaf nodes and concurrent processing for sibling
    branches to maximise throughput.
    """
    total = _count(tree)
    counter = [0]
    sem = asyncio.Semaphore(15)  # max 15 concurrent Gemini calls

    def _tick(n: int = 1) -> None:
        counter[0] += n
        if on_progress:
            on_progress(counter[0], total)

    async def _summarize_one(node: TreeNode) -> None:
        if _can_auto_summarize(node):
            node.summary = _auto_summary(node)
            _tick()
            return
        async with sem:
            node.summary = await summarize_node(node)
        _tick()

    async def _summarize_leaves_batched(leaves: List[TreeNode]) -> None:
        """Summarize leaf nodes in batches to reduce API calls."""
        # Separate trivial nodes (auto-summarize) from those needing API
        trivial = [n for n in leaves if _can_auto_summarize(n)]
        needs_api = [n for n in leaves if not _can_auto_summarize(n)]

        # Auto-summarize trivial nodes instantly
        for n in trivial:
            n.summary = _auto_summary(n)
            _tick()

        # Batch the rest
        for i in range(0, len(needs_api), _BATCH_SIZE):
            batch = needs_api[i : i + _BATCH_SIZE]
            if len(batch) == 1:
                await _summarize_one(batch[0])
            else:
                async with sem:
                    summaries = await _summarize_batch(batch)
                for node, summary in zip(batch, summaries):
                    node.summary = summary
                _tick(len(batch))

    async def _walk(node: TreeNode) -> None:
        if not node.children:
            return

        leaves = [c for c in node.children if not c.children]
        branches = [c for c in node.children if c.children]

        # Summarize all leaf children in batches
        if leaves:
            await _summarize_leaves_batched(leaves)

        # Process sibling branches CONCURRENTLY (each branch does its
        # own bottom-up walk; the semaphore limits actual API calls)
        if branches:
            await asyncio.gather(*[_walk(b) for b in branches])

        # Now summarize the branch nodes themselves concurrently
        if branches:
            await asyncio.gather(*[_summarize_one(b) for b in branches])

        # Finally summarize this node (all children done)
        await _summarize_one(node)

    if not tree.children:
        await _summarize_one(tree)
    else:
        await _walk(tree)

    return tree


def _count(node: TreeNode) -> int:
    return 1 + sum(_count(c) for c in node.children)
