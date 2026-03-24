import os
import tempfile
from pathlib import Path

import pytest

from backend.core.parser import count_nodes, get_supported_language, parse_file, parse_repo


@pytest.fixture
def sample_repo(tmp_path):
    """Create a small sample repo with Python files."""
    # Python file with class and function
    (tmp_path / "main.py").write_text(
        '''"""Main module docstring."""
import os
from pathlib import Path


class Calculator:
    """A simple calculator."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b


def greet(name: str) -> str:
    """Greet a person."""
    return f"Hello, {name}!"
''',
        encoding="utf-8",
    )

    # Another Python file
    (tmp_path / "utils.py").write_text(
        '''import json


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
''',
        encoding="utf-8",
    )

    # A sub-directory with a file
    sub = tmp_path / "helpers"
    sub.mkdir()
    (sub / "math_utils.py").write_text(
        '''def multiply(a, b):
    return a * b
''',
        encoding="utf-8",
    )

    # Hidden dir and node_modules (should be skipped)
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "secret.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module.exports = {}", encoding="utf-8")

    return tmp_path


def test_get_supported_language():
    assert get_supported_language("app.py") == "python"
    assert get_supported_language("index.js") == "javascript"
    assert get_supported_language("App.tsx") == "typescript"
    assert get_supported_language("main.go") is None
    assert get_supported_language("README.md") is None


def test_parse_file_python(sample_repo):
    tree = parse_file(str(sample_repo / "main.py"), str(sample_repo))
    assert tree.name == "main.py"
    assert tree.type == "file"
    assert tree.language == "python"
    assert tree.imports is not None
    assert len(tree.imports) == 2

    # Should have a class and a function
    names = {child.name for child in tree.children}
    assert "Calculator" in names
    assert "greet" in names

    # Calculator should have methods
    calc = next(c for c in tree.children if c.name == "Calculator")
    method_names = {m.name for m in calc.children}
    assert "add" in method_names
    assert "subtract" in method_names


def test_parse_repo_structure(sample_repo):
    tree = parse_repo(str(sample_repo))
    assert tree.type == "directory"

    # Top-level should include main.py, utils.py, helpers/
    child_names = {c.name for c in tree.children}
    assert "main.py" in child_names
    assert "utils.py" in child_names
    assert "helpers" in child_names

    # Hidden dir and node_modules should be skipped
    assert ".hidden" not in child_names
    assert "node_modules" not in child_names


def test_parse_repo_skips_hidden_and_node_modules(sample_repo):
    tree = parse_repo(str(sample_repo))
    all_names = _collect_names(tree)
    assert ".hidden" not in all_names
    assert "node_modules" not in all_names
    assert "secret.py" not in all_names
    assert "pkg.js" not in all_names


def test_count_nodes(sample_repo):
    tree = parse_repo(str(sample_repo))
    total = count_nodes(tree)
    # root dir + main.py + Calculator + add + subtract + greet + utils.py + load_config + helpers/ + math_utils.py + multiply
    assert total >= 10


def test_code_snippet_truncation(sample_repo):
    tree = parse_file(str(sample_repo / "main.py"), str(sample_repo))
    greet = next(c for c in tree.children if c.name == "greet")
    assert greet.code_snippet is not None
    assert len(greet.code_snippet.split("\n")) <= 31  # 30 + possible truncation marker


def _collect_names(node):
    names = {node.name}
    for child in node.children:
        names.update(_collect_names(child))
    return names
