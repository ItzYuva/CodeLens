import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.summarizer import summarize_node, summarize_tree, _strip_code_fences
from backend.models.schemas import NodeSummary, TreeNode


def _make_function_node(name="my_func"):
    return TreeNode(
        name=name,
        type="function",
        language="python",
        path=f"module.py:{name}",
        params=["x", "y"],
        code_snippet=f"def {name}(x, y):\n    return x + y",
    )


def _make_tree():
    """Build a small tree: directory -> file -> function."""
    func = _make_function_node("add")
    file_node = TreeNode(
        name="math.py",
        type="file",
        language="python",
        path="math.py",
        imports=["import os"],
        children=[func],
    )
    root = TreeNode(
        name="src",
        type="directory",
        path="src",
        children=[file_node],
    )
    return root


MOCK_RESPONSE = json.dumps({
    "summary": "This function adds two numbers together.",
    "exports": ["add"],
    "dependencies": [],
    "key_signatures": ["add(x, y)"],
})


def test_strip_code_fences():
    assert _strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fences('{"a": 1}') == '{"a": 1}'
    assert _strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'


@pytest.mark.asyncio
async def test_summarize_node_success():
    node = _make_function_node()
    with patch("backend.core.summarizer.call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = MOCK_RESPONSE
        summary = await summarize_node(node)

    assert isinstance(summary, NodeSummary)
    assert "adds two numbers" in summary.summary
    assert "add" in summary.exports


@pytest.mark.asyncio
async def test_summarize_node_fallback_on_failure():
    node = _make_function_node()
    with patch("backend.core.summarizer.call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.side_effect = Exception("API error")
        summary = await summarize_node(node)

    assert isinstance(summary, NodeSummary)
    assert "my_func" in summary.summary
    assert summary.exports == ["my_func"]


@pytest.mark.asyncio
async def test_summarize_tree_full():
    tree = _make_tree()
    progress_calls = []

    def on_progress(current, total):
        progress_calls.append((current, total))

    with patch("backend.core.summarizer.call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = MOCK_RESPONSE
        result = await summarize_tree(tree, on_progress=on_progress)

    # All 3 nodes should be summarized
    assert result.summary is not None
    assert result.children[0].summary is not None
    assert result.children[0].children[0].summary is not None

    # Progress should have been called 3 times
    assert len(progress_calls) == 3
    assert progress_calls[-1] == (3, 3)


@pytest.mark.asyncio
async def test_summarize_tree_bottom_up_order():
    """Verify children are summarized before parents."""
    tree = _make_tree()
    call_order = []

    async def mock_gemini(prompt):
        # Extract the node type from the prompt
        if "Summarize this python function" in prompt:
            call_order.append("function:add")
        elif "Summarize this python file" in prompt:
            call_order.append("file:math.py")
        elif "Summarize this directory" in prompt:
            call_order.append("directory:src")
        return MOCK_RESPONSE

    with patch("backend.core.summarizer.call_gemini", side_effect=mock_gemini):
        await summarize_tree(tree)

    assert call_order.index("function:add") < call_order.index("file:math.py")
    assert call_order.index("file:math.py") < call_order.index("directory:src")
