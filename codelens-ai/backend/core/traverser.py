import asyncio
import json
import re
import time
from difflib import SequenceMatcher
from typing import Callable, List, Optional

from backend.core.summarizer import call_gemini, _strip_code_fences
from backend.models.schemas import ThinkingStep, TreeNode


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _collect_by_type(node: TreeNode, node_type: str) -> List[TreeNode]:
    results = []
    if node.type == node_type:
        results.append(node)
    for child in node.children:
        results.extend(_collect_by_type(child, node_type))
    return results


def _best_match(name: str, available: List[str]) -> Optional[str]:
    """Fuzzy-match a name against available names."""
    # Exact match
    if name in available:
        return name
    # Case-insensitive
    lower_map = {a.lower(): a for a in available}
    if name.lower() in lower_map:
        return lower_map[name.lower()]
    # Without extension
    stem = name.rsplit(".", 1)[0] if "." in name else name
    for a in available:
        a_stem = a.rsplit(".", 1)[0] if "." in a else a
        if stem.lower() == a_stem.lower():
            return a
    # Sequence similarity
    best, best_score = None, 0.0
    for a in available:
        score = SequenceMatcher(None, name.lower(), a.lower()).ratio()
        if score > best_score:
            best, best_score = a, score
    if best_score > 0.6:
        return best
    return None


def parse_selection(response: str, available_names: List[str]) -> List[str]:
    """Parse a JSON array from Gemini and fuzzy-match against available names."""
    cleaned = _strip_code_fences(response)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract array with regex
        match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                return available_names[:3]
        else:
            return available_names[:3]

    if not isinstance(parsed, list):
        return available_names[:3]

    matched = []
    for name in parsed:
        if not isinstance(name, str):
            continue
        m = _best_match(name, available_names)
        if m and m not in matched:
            matched.append(m)

    return matched if matched else available_names[:3]


def _build_dir_prompt(query: str, dirs: List[TreeNode]) -> str:
    entries = []
    for d in dirs:
        summary = d.summary.summary if d.summary else "No description available"
        exports = ", ".join(d.summary.exports[:5]) if d.summary else ""
        entries.append(f"- **{d.name}/**: {summary}\n  Key contents: {exports}")

    return f"""You are navigating a codebase to answer this question: "{query}"

Here are the top-level directories and their descriptions:
{chr(10).join(entries)}

Which directories are most likely to contain code relevant to answering the question?
Return ONLY a JSON array of directory names. Select 1-5 most relevant.
Example: ["src", "lib", "utils"]"""


def _build_file_prompt(query: str, files: List[TreeNode]) -> str:
    entries = []
    for f in files:
        summary = f.summary.summary if f.summary else "No description available"
        exports = ", ".join(f.summary.exports[:5]) if f.summary else ""
        deps = ", ".join(f.summary.dependencies[:5]) if f.summary else ""
        entries.append(
            f"- **{f.path}**: {summary}\n  Exports: {exports}\n  Dependencies: {deps}"
        )

    return f"""You are navigating a codebase to answer this question: "{query}"

You're now inside these directories. Here are the files:
{chr(10).join(entries)}

Which files are most relevant to answering the question?
Return ONLY a JSON array of file names (with extensions). Select 1-8 most relevant.
Example: ["auth.py", "middleware.py", "config.py"]"""


def _build_func_prompt(query: str, file_node: TreeNode) -> str:
    entries = []
    for child in file_node.children:
        summary = child.summary.summary if child.summary else "No description available"
        sigs = ", ".join(child.summary.key_signatures[:3]) if child.summary else ""
        entries.append(
            f"- **{child.name}** ({child.type}): {summary}\n  Signature: {sigs}"
        )

    return f"""You are navigating a codebase to answer this question: "{query}"

You're looking at **{file_node.path}**. It contains:
{chr(10).join(entries)}

Which functions/classes are most relevant to answering the question?
Return ONLY a JSON array of names. Select 1-5 most relevant.
Example: ["validate_token", "AuthManager"]"""


async def traverse_tree(
    query: str,
    tree: TreeNode,
    bm25_candidates: Optional[List[TreeNode]] = None,
    on_thinking: Optional[Callable[[ThinkingStep], None]] = None,
    max_depth: int = 4,
    max_selected_nodes: int = 15,
    max_context_tokens: int = 25000,
) -> List[TreeNode]:
    """Lazily traverse the summary tree, selecting relevant branches via LLM."""

    bm25_paths = set()
    if bm25_candidates:
        bm25_paths = {n.path for n in bm25_candidates}

    # Collect top-level directories and files
    top_dirs = [c for c in tree.children if c.type == "directory"]
    top_files = [c for c in tree.children if c.type == "file"]

    # STEP 1 -- Directory-level selection
    # For small repos (≤ 5 top-level dirs), skip the LLM call and scan all dirs
    selected_dirs: List[TreeNode] = []
    if top_dirs:
        if len(top_dirs) <= 5:
            # Small repo — just use all directories, no LLM call needed
            selected_dirs = list(top_dirs)
        else:
            prompt = _build_dir_prompt(query, top_dirs)
            try:
                response = await call_gemini(prompt)
                dir_names = parse_selection(response, [d.name for d in top_dirs])
            except Exception:
                # Fallback: pick dirs containing BM25 candidates, or first 3
                dir_names = []
                for d in top_dirs:
                    for child in d.children:
                        if child.path in bm25_paths:
                            dir_names.append(d.name)
                            break
                if not dir_names:
                    dir_names = [d.name for d in top_dirs[:3]]
            selected_dirs = [d for d in top_dirs if d.name in dir_names]

        if on_thinking:
            for d in selected_dirs:
                file_count = sum(1 for c in d.children if c.type == "file")
                on_thinking(ThinkingStep(
                    step_type="exploring",
                    message=f"Exploring: {d.name}/ directory ({file_count} files)",
                    timestamp=time.time(),
                ))

    # STEP 2 -- File-level selection
    candidate_files: List[TreeNode] = list(top_files)
    for d in selected_dirs:
        candidate_files.extend(c for c in d.children if c.type == "file")
        # Also recurse one level into subdirs
        for sub in d.children:
            if sub.type == "directory":
                candidate_files.extend(c for c in sub.children if c.type == "file")

    # Include BM25 candidates even if their parent wasn't selected
    if bm25_candidates:
        existing_paths = {f.path for f in candidate_files}
        for bc in bm25_candidates:
            if bc.path not in existing_paths:
                candidate_files.append(bc)

    if not candidate_files:
        return []

    # For small file sets (≤ 8), skip the LLM call and use all files
    if len(candidate_files) <= 8:
        selected_files = list(candidate_files)
    else:
        prompt = _build_file_prompt(query, candidate_files)
        try:
            response = await call_gemini(prompt)
            file_names = parse_selection(response, [f.name for f in candidate_files])
        except Exception:
            # Fallback: use BM25 candidates or first 5
            if bm25_candidates:
                file_names = [f.name for f in bm25_candidates[:5]]
            else:
                file_names = [f.name for f in candidate_files[:5]]

        selected_files = [f for f in candidate_files if f.name in file_names]
    # Deduplicate by path
    seen_paths = set()
    deduped = []
    for f in selected_files:
        if f.path not in seen_paths:
            seen_paths.add(f.path)
            deduped.append(f)
    selected_files = deduped

    if on_thinking:
        for f in selected_files:
            main_export = ""
            if f.summary and f.summary.exports:
                main_export = ", ".join(f.summary.exports[:2])
            elif f.children:
                main_export = ", ".join(c.name for c in f.children[:2])
            suffix = f" -> {main_export}" if main_export else ""
            on_thinking(ThinkingStep(
                step_type="reading",
                message=f"Reading: {f.path}{suffix}",
                timestamp=time.time(),
            ))

    # STEP 3 -- Function/class-level selection within large files
    selected_nodes: List[TreeNode] = []
    for f in selected_files:
        if not f.children:
            selected_nodes.append(f)
            continue

        if len(f.children) <= 5:
            selected_nodes.extend(f.children)
            continue

        # Ask LLM to pick relevant functions/classes
        prompt = _build_func_prompt(query, f)
        try:
            response = await call_gemini(prompt)
            func_names = parse_selection(response, [c.name for c in f.children])
            selected = [c for c in f.children if c.name in func_names]
            if not selected:
                selected = f.children[:5]
        except Exception:
            selected = f.children[:5]

        selected_nodes.extend(selected)

        if on_thinking:
            for s in selected:
                on_thinking(ThinkingStep(
                    step_type="reading",
                    message=f"Reading: {f.path} -> {s.name} ({s.type})",
                    timestamp=time.time(),
                ))

    # STEP 4 -- Enforce token budget
    if len(selected_nodes) > max_selected_nodes:
        # Prioritize BM25 candidates
        bm25_set = set()
        non_bm25 = []
        for n in selected_nodes:
            parent_path = n.path.rsplit(":", 1)[0] if ":" in n.path else n.path
            if parent_path in bm25_paths or n.path in bm25_paths:
                bm25_set.add(id(n))
            else:
                non_bm25.append(n)
        prioritized = [n for n in selected_nodes if id(n) in bm25_set]
        prioritized.extend(non_bm25)
        selected_nodes = prioritized[:max_selected_nodes]

    # Estimate tokens and truncate if needed
    total_tokens = sum(_estimate_tokens(n.code_snippet or "") for n in selected_nodes)
    if total_tokens > max_context_tokens:
        # Sort by snippet length descending, truncate longest first
        by_length = sorted(
            selected_nodes,
            key=lambda n: len(n.code_snippet or ""),
            reverse=True,
        )
        for node in by_length:
            if total_tokens <= max_context_tokens:
                break
            if node.code_snippet:
                old_tokens = _estimate_tokens(node.code_snippet)
                lines = node.code_snippet.split("\n")
                node.code_snippet = "\n".join(lines[:15]) + "\n# ... truncated"
                new_tokens = _estimate_tokens(node.code_snippet)
                total_tokens -= (old_tokens - new_tokens)

    return selected_nodes
