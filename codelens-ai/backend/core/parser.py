from pathlib import Path
from typing import Optional

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser

from backend.config import MAX_FILES_PER_REPO
from backend.models.schemas import TreeNode

PYTHON_LANGUAGE = Language(tspython.language())
JAVASCRIPT_LANGUAGE = Language(tsjavascript.language())
TYPESCRIPT_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage", ".idea",
    ".vscode", ".DS_Store",
}

RAW_READ_FILES = {
    "README.md", "readme.md", "package.json", "pyproject.toml",
    "requirements.txt", "Dockerfile", "docker-compose.yml",
}

EXTENSION_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def get_supported_language(file_path: str) -> Optional[str]:
    ext = Path(file_path).suffix
    return EXTENSION_MAP.get(ext)


def _get_ts_language(language: str, file_path: str) -> Language:
    if language == "python":
        return PYTHON_LANGUAGE
    if language == "javascript":
        return JAVASCRIPT_LANGUAGE
    if language == "typescript":
        if file_path.endswith(".tsx"):
            return TSX_LANGUAGE
        return TYPESCRIPT_LANGUAGE
    raise ValueError(f"Unsupported language: {language}")


def _extract_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _truncate(text: str, max_lines: int) -> str:
    lines = text.split("\n")
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + "\n# ... truncated"
    return text


def _get_docstring(node, source: bytes) -> Optional[str]:
    """Extract docstring from a Python function/class body."""
    body = None
    for child in node.children:
        if child.type in ("block", "body"):
            body = child
            break
    if body is None:
        return None
    for child in body.children:
        if child.type == "expression_statement":
            expr = child.children[0] if child.children else None
            if expr and expr.type == "string":
                return _extract_text(expr, source).strip("\"'")
        elif child.type not in ("comment", "newline"):
            break
    return None


def _get_params(node, source: bytes) -> list[str]:
    """Extract parameter names from a function definition."""
    for child in node.children:
        if child.type == "parameters" or child.type == "formal_parameters":
            params = []
            for param in child.children:
                if param.type in ("identifier", "typed_parameter", "typed_default_parameter",
                                  "default_parameter", "required_parameter",
                                  "optional_parameter"):
                    name = param.children[0] if param.children else param
                    params.append(_extract_text(name, source))
                elif param.type == "assignment_pattern":
                    if param.children:
                        params.append(_extract_text(param.children[0], source))
            return params
    return []


def _parse_python(root_node, source: bytes, file_path: str, rel_path: str) -> TreeNode:
    children = []
    imports = []

    for node in root_node.children:
        if node.type in ("import_statement", "import_from_statement"):
            imports.append(_extract_text(node, source))

        elif node.type == "class_definition":
            class_name = None
            for child in node.children:
                if child.type == "identifier":
                    class_name = _extract_text(child, source)
                    break
            class_children = []
            for child in node.children:
                if child.type == "block":
                    for block_child in child.children:
                        if block_child.type == "function_definition":
                            method_name = None
                            for mc in block_child.children:
                                if mc.type == "identifier":
                                    method_name = _extract_text(mc, source)
                                    break
                            class_children.append(TreeNode(
                                name=method_name or "unknown",
                                type="method",
                                language="python",
                                path=f"{rel_path}:{class_name}.{method_name}",
                                params=_get_params(block_child, source),
                                code_snippet=_truncate(_extract_text(block_child, source), 30),
                            ))
            children.append(TreeNode(
                name=class_name or "unknown",
                type="class",
                language="python",
                path=f"{rel_path}:{class_name}",
                children=class_children,
            ))

        elif node.type == "function_definition":
            func_name = None
            for child in node.children:
                if child.type == "identifier":
                    func_name = _extract_text(child, source)
                    break
            children.append(TreeNode(
                name=func_name or "unknown",
                type="function",
                language="python",
                path=f"{rel_path}:{func_name}",
                params=_get_params(node, source),
                code_snippet=_truncate(_extract_text(node, source), 30),
            ))

    return TreeNode(
        name=Path(file_path).name,
        type="file",
        language="python",
        path=rel_path,
        imports=imports if imports else None,
        children=children,
    )


def _parse_js_ts(root_node, source: bytes, file_path: str, rel_path: str, language: str) -> TreeNode:
    children = []
    imports = []

    for node in root_node.children:
        if node.type in ("import_statement", "import_declaration"):
            imports.append(_extract_text(node, source))

        elif node.type == "export_statement":
            # Look inside export for class/function declarations
            for child in node.children:
                _extract_js_declaration(child, source, rel_path, language, children)

        elif node.type in ("class_declaration", "function_declaration"):
            _extract_js_declaration(node, source, rel_path, language, children)

        elif node.type in ("lexical_declaration", "variable_declaration"):
            _extract_arrow_functions(node, source, rel_path, language, children)

    return TreeNode(
        name=Path(file_path).name,
        type="file",
        language=language,
        path=rel_path,
        imports=imports if imports else None,
        children=children,
    )


def _extract_js_declaration(node, source: bytes, rel_path: str, language: str, children: list):
    if node.type == "class_declaration":
        class_name = None
        for child in node.children:
            if child.type == "identifier" or child.type == "type_identifier":
                class_name = _extract_text(child, source)
                break
        class_children = []
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "method_definition":
                        method_name = None
                        for mc in member.children:
                            if mc.type == "property_identifier":
                                method_name = _extract_text(mc, source)
                                break
                        class_children.append(TreeNode(
                            name=method_name or "unknown",
                            type="method",
                            language=language,
                            path=f"{rel_path}:{class_name}.{method_name}",
                            params=_get_params(member, source),
                            code_snippet=_truncate(_extract_text(member, source), 30),
                        ))
        children.append(TreeNode(
            name=class_name or "unknown",
            type="class",
            language=language,
            path=f"{rel_path}:{class_name}",
            children=class_children,
        ))

    elif node.type == "function_declaration":
        func_name = None
        for child in node.children:
            if child.type == "identifier":
                func_name = _extract_text(child, source)
                break
        children.append(TreeNode(
            name=func_name or "unknown",
            type="function",
            language=language,
            path=f"{rel_path}:{func_name}",
            params=_get_params(node, source),
            code_snippet=_truncate(_extract_text(node, source), 30),
        ))

    elif node.type in ("lexical_declaration", "variable_declaration"):
        _extract_arrow_functions(node, source, rel_path, language, children)


def _extract_arrow_functions(node, source: bytes, rel_path: str, language: str, children: list):
    for child in node.children:
        if child.type == "variable_declarator":
            name_node = None
            value_node = None
            for vc in child.children:
                if vc.type == "identifier":
                    name_node = vc
                elif vc.type == "arrow_function":
                    value_node = vc
            if name_node and value_node:
                func_name = _extract_text(name_node, source)
                children.append(TreeNode(
                    name=func_name,
                    type="function",
                    language=language,
                    path=f"{rel_path}:{func_name}",
                    params=_get_params(value_node, source),
                    code_snippet=_truncate(_extract_text(value_node, source), 30),
                ))


def parse_file(file_path: str, repo_root: str) -> TreeNode:
    """Parse a single source file into a TreeNode using tree-sitter."""
    rel_path = str(Path(file_path).relative_to(repo_root)).replace("\\", "/")
    language = get_supported_language(file_path)

    if language is None:
        # Raw-read for config/doc files
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        return TreeNode(
            name=Path(file_path).name,
            type="file",
            path=rel_path,
            code_snippet=_truncate(source, 200),
        )

    source_bytes = Path(file_path).read_bytes()
    ts_lang = _get_ts_language(language, file_path)
    parser = Parser(ts_lang)
    tree = parser.parse(source_bytes)

    if language == "python":
        return _parse_python(tree.root_node, source_bytes, file_path, rel_path)
    else:
        return _parse_js_ts(tree.root_node, source_bytes, file_path, rel_path, language)


def parse_repo(repo_path: str) -> TreeNode:
    """Parse an entire repo directory into a hierarchical TreeNode."""
    repo_root = Path(repo_path)

    def walk_dir(dir_path: Path) -> TreeNode:
        children = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            entries = []

        for entry in entries:
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue

            if entry.is_dir():
                dir_node = walk_dir(entry)
                if dir_node.children:  # only include non-empty directories
                    children.append(dir_node)
            elif entry.is_file():
                lang = get_supported_language(str(entry))
                if lang is not None or entry.name in RAW_READ_FILES:
                    try:
                        file_node = parse_file(str(entry), str(repo_root))
                        children.append(file_node)
                    except Exception:
                        pass  # skip unparseable files

        rel_path = str(dir_path.relative_to(repo_root)).replace("\\", "/")
        if rel_path == ".":
            rel_path = ""

        return TreeNode(
            name=dir_path.name,
            type="directory",
            path=rel_path,
            children=children,
        )

    root = walk_dir(repo_root)
    total = count_nodes(root)
    if total > MAX_FILES_PER_REPO:
        raise RuntimeError(f"Repository has {total} nodes, exceeding the limit of {MAX_FILES_PER_REPO}")
    return root


def count_nodes(tree: TreeNode) -> int:
    """Recursively count all nodes in the tree."""
    return 1 + sum(count_nodes(child) for child in tree.children)
