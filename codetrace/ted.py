"""Zhang-Shasha 树编辑距离（纯 Python 自研实现）。

不依赖 zss/Cython，保证在任意环境可安装运行。
规模控制（方案 §3.1.2 的分层度量）：当子树节点数超过 max_nodes 时，
自动降级为节点多重集差异度量（线性复杂度），避免复杂度爆炸。
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Optional

DEFAULT_MAX_NODES = 300


class TNode:
    __slots__ = ("label", "children", "pid")

    def __init__(self, label: str, children: Optional[list] = None):
        self.label = label
        self.children = children if children is not None else []
        self.pid = 0

    def __repr__(self) -> str:  # pragma: no cover
        return f"TNode({self.label}, {len(self.children)})"


def node_count(n: TNode) -> int:
    total = 1
    for c in n.children:
        total += node_count(c)
    return total


def serialize(n: TNode) -> str:
    if not n.children:
        return n.label
    return n.label + "(" + ",".join(serialize(c) for c in n.children) + ")"


def multiset(n: TNode) -> Counter:
    counter: Counter = Counter()
    stack = [n]
    while stack:
        cur = stack.pop()
        counter[cur.label] += 1
        stack.extend(cur.children)
    return counter


def multiset_distance(a: TNode, b: TNode) -> int:
    """降级度量：节点标签多重集的对称差规模。"""
    ca, cb = multiset(a), multiset(b)
    diff = 0
    for key in set(ca) | set(cb):
        diff += abs(ca.get(key, 0) - cb.get(key, 0))
    return diff


def _rename_cost(a: TNode, b: TNode) -> int:
    return 0 if a.label == b.label else 1


def _postorder(root: TNode) -> list[TNode]:
    out: list[TNode] = []

    def rec(n: TNode) -> None:
        for c in n.children:
            rec(c)
        n.pid = len(out) + 1
        out.append(n)

    rec(root)
    return out


def _leftmost(nodes: list[TNode]) -> dict[int, int]:
    lm: dict[int, int] = {}
    for n in sorted(nodes, key=lambda x: x.pid):
        if not n.children:
            lm[n.pid] = n.pid
        else:
            lm[n.pid] = lm[min(c.pid for c in n.children)]
    return lm


def _keyroots(nodes: list[TNode], lm: dict[int, int]) -> list[int]:
    total = len(nodes)
    krs = []
    for n in sorted(nodes, key=lambda x: x.pid):
        if n.pid == total or lm.get(n.pid) != lm.get(n.pid + 1):
            krs.append(n.pid)
    return krs


def tree_edit_distance(a: TNode, b: TNode, rename_cost: Callable[[TNode, TNode], int] = _rename_cost) -> int:
    """精确 Zhang-Shasha 树编辑距离（插入/删除代价 1）。"""
    A = _postorder(a)
    B = _postorder(b)
    n, m = len(A), len(B)
    if n == 0 or m == 0:
        return max(n, m)
    la, lb = _leftmost(A), _leftmost(B)
    kra, krb = _keyroots(A, la), _keyroots(B, lb)
    amap = {x.pid: x for x in A}
    bmap = {y.pid: y for y in B}

    td = [[0] * (m + 1) for _ in range(n + 1)]
    for i in kra:
        for j in krb:
            fd = [[0] * (m + 1) for _ in range(n + 1)]
            i0 = la[i] - 1
            j0 = lb[j] - 1
            for x in range(i0 + 1, i + 1):
                fd[x][j0] = fd[x - 1][j0] + 1
            for y in range(j0 + 1, j + 1):
                fd[i0][y] = fd[i0][y - 1] + 1
            for x in range(i0 + 1, i + 1):
                for y in range(j0 + 1, j + 1):
                    cost = rename_cost(amap[x], bmap[y])
                    if la[x] == la[i] and lb[y] == lb[j]:
                        fd[x][y] = min(
                            fd[x - 1][y] + 1,
                            fd[x][y - 1] + 1,
                            fd[x - 1][y - 1] + cost,
                        )
                        td[x][y] = fd[x][y]
                    else:
                        fd[x][y] = min(
                            fd[x - 1][y] + 1,
                            fd[x][y - 1] + 1,
                            fd[x - 1][y - 1] + cost,
                        )
    return td[n][m]


def layered_distance(a: TNode, b: TNode, max_nodes: int = DEFAULT_MAX_NODES) -> tuple[float, bool]:
    """分层语义差异度量。

    返回 (差异量, 是否降级)。子树规模超阈值时降级为多重集差异（线性复杂度）。
    """
    na, nb = node_count(a), node_count(b)
    if na > max_nodes or nb > max_nodes:
        return float(multiset_distance(a, b)), True
    return float(tree_edit_distance(a, b)), False
