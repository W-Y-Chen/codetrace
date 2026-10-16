"""AST 解析与函数级子树提取。

v0.1 使用 Python 标准库 ast（零依赖、保证可运行），仅支持 Python；
多语言支持在二期通过 tree-sitter 接入，接口保持不变。
"""
from __future__ import annotations

import ast
import re
from typing import Optional

from .events import sha256_hex
from .ted import TNode

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$|^[a-z][a-z0-9]*$")
CAMEL_RE = re.compile(r"^[a-z]+([A-Z][a-z0-9]*)+$")


class ParseError(ValueError):
    pass


def _label(node: ast.AST) -> str:
    t = type(node).__name__
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"FunctionDef:{node.name}"
    if isinstance(node, ast.ClassDef):
        return f"ClassDef:{node.name}"
    if isinstance(node, ast.Name):
        return f"Name:{node.id}"
    if isinstance(node, ast.Attribute):
        return f"Attribute:{node.attr}"
    if isinstance(node, ast.arg):
        return f"arg:{node.arg}"
    if isinstance(node, ast.Constant):
        return f"Constant:{type(node.value).__name__}"
    if isinstance(node, ast.Import):
        return "Import"
    if isinstance(node, ast.ImportFrom):
        return f"ImportFrom:{node.module or ''}"
    return t


def build_ir(root: ast.AST) -> TNode:
    node = TNode(_label(root))
    for child in ast.iter_child_nodes(root):
        node.children.append(build_ir(child))
    return node


def parse_code(code: str) -> TNode:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ParseError(f"代码无法解析: {exc}") from exc
    return build_ir(tree)


def try_parse_code(code: str) -> Optional[TNode]:
    try:
        return parse_code(code)
    except ParseError:
        return None


def ir_hash(ir: TNode) -> str:
    from .ted import serialize

    return sha256_hex(serialize(ir).encode("utf-8"))


def function_subtrees(ir: TNode) -> dict[str, TNode]:
    """提取函数级子树，键为函数名。"""
    found: dict[str, TNode] = {}
    stack = [ir]
    while stack:
        cur = stack.pop()
        if cur.label.startswith("FunctionDef:"):
            name = cur.label.split(":", 1)[1]
            found.setdefault(name, cur)
        stack.extend(cur.children)
    return found


def identifiers(code: str) -> list[str]:
    return IDENT_RE.findall(code)


CAMEL_SPLIT_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def split_identifier(word: str) -> list[str]:
    """把 count_items / countItems 拆成 ['count', 'items']。"""
    parts: list[str] = []
    for chunk in word.split("_"):
        if not chunk:
            continue
        if any(c.isupper() for c in chunk[1:]):
            parts.extend(m.lower() for m in CAMEL_SPLIT_RE.findall(chunk))
        else:
            parts.append(chunk.lower())
    return parts


def identifier_tokens(code: str) -> list[str]:
    out: list[str] = []
    for word in identifiers(code):
        out.extend(split_identifier(word))
    return out


def comment_lines(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip().startswith("#"))


def _is_snake(word: str) -> bool:
    return "_" in word and not any(c.isupper() for c in word[1:])


def _is_camel(word: str) -> bool:
    return "_" not in word and any(c.isupper() for c in word[1:])


def style_features(code: str) -> dict:
    """代码风格特征（P4 通道输入）。

    命名风格只统计**多词标识符**：像 items / counts / kv 这类单词标识符
    在任何风格下都相同，若计入会把作者特征稀释掉。
    """
    distinct = sorted(set(identifiers(code)))
    lines = [l for l in code.splitlines()]
    non_empty = [l for l in lines if l.strip()]
    if not distinct:
        return {
            "snake_ratio": 0.0,
            "camel_ratio": 0.0,
            "avg_ident_len": 0.0,
            "comment_density": 0.0,
            "indent_width": 0.0,
            "multiword_snake": 0.0,
            "multiword_camel": 0.0,
        }

    multiword = [i for i in distinct if _is_snake(i) or _is_camel(i)]
    if multiword:
        m_snake = sum(1 for i in multiword if _is_snake(i)) / len(multiword)
        m_camel = sum(1 for i in multiword if _is_camel(i)) / len(multiword)
    else:
        m_snake = m_camel = 0.0

    comment_density = (comment_lines(code) / len(non_empty)) if non_empty else 0.0
    return {
        "snake_ratio": round(sum(1 for i in distinct if SNAKE_RE.match(i)) / len(distinct), 4),
        "camel_ratio": round(sum(1 for i in distinct if CAMEL_RE.match(i)) / len(distinct), 4),
        "avg_ident_len": round(sum(len(i) for i in distinct) / len(distinct), 4),
        "comment_density": round(comment_density, 4),
        "indent_width": float(_mode_indent(non_empty)),
        "multiword_snake": round(m_snake, 4),
        "multiword_camel": round(m_camel, 4),
    }


def _mode_indent(lines: list[str]) -> int:
    widths = []
    for line in lines:
        stripped = line.lstrip(" ")
        w = len(line) - len(stripped)
        if w:
            widths.append(w)
    if not widths:
        return 0
    return max(set(widths), key=widths.count)
