import asyncio
import json
import re
from typing import Callable, Optional

from google import genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL
from backend.models.schemas import NodeSummary, TreeNode


def _get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from Gemini responses."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


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


async def call_gemini(prompt: str) -> str:
    """Call Gemini Flash API with retries."""
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
                await asyncio.sleep(1 * (2 ** attempt))

    raise last_error


async def summarize_node(node: TreeNode) -> NodeSummary:
    """Summarize a single node using Gemini."""
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
    """Traverse the tree bottom-up and summarize every node."""
    total = _count(tree)
    counter = [0]

    async def _walk(node: TreeNode) -> None:
        # Recurse into children first (post-order)
        for child in node.children:
            await _walk(child)

        # Summarize this node
        node.summary = await summarize_node(node)
        counter[0] += 1

        if on_progress:
            on_progress(counter[0], total)

        # Rate-limit delay
        await asyncio.sleep(0.1)

    await _walk(tree)
    return tree


def _count(node: TreeNode) -> int:
    return 1 + sum(_count(c) for c in node.children)
