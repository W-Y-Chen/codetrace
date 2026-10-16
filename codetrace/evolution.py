"""代码语义演化图构建与分层语义差异度量（方案 §3.1.2，创新一）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .astutil import function_subtrees, try_parse_code
from .events import SnapshotEvent
from .ted import DEFAULT_MAX_NODES, TNode, layered_distance, node_count


@dataclass
class Snapshot:
    snapshot_id: str
    ts: int
    code: str
    ir: Optional[TNode] = None
    funcs: dict[str, TNode] = field(default_factory=dict)
    parse_ok: bool = True

    @property
    def total_nodes(self) -> int:
        if self.ir is None:
            return 0
        if self.funcs:
            return sum(node_count(f) for f in self.funcs.values())
        return node_count(self.ir)


def make_snapshot(ev: SnapshotEvent) -> Snapshot:
    ir = try_parse_code(ev.code) if ev.code else None
    funcs = function_subtrees(ir) if ir is not None else {}
    return Snapshot(
        snapshot_id=ev.snapshot_id or f"snap-{ev.ts}",
        ts=ev.ts,
        code=ev.code,
        ir=ir,
        funcs=funcs,
        parse_ok=ir is not None,
    )


@dataclass
class EvolutionEdge:
    from_id: str
    to_id: str
    ts: int
    dsem: float
    raw_cost: float
    degraded: bool
    from_empty: bool = False
    per_func: dict[str, float] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def _diff_snapshots(a: Snapshot, b: Snapshot, max_nodes: int) -> EvolutionEdge:
    per_func: dict[str, float] = {}
    degraded = False
    cost = 0.0

    if a.funcs or b.funcs:
        common = set(a.funcs) & set(b.funcs)
        added = sorted(set(b.funcs) - set(a.funcs))
        removed = sorted(set(a.funcs) - set(b.funcs))
        for name in sorted(common):
            d, deg = layered_distance(a.funcs[name], b.funcs[name], max_nodes=max_nodes)
            degraded = degraded or deg
            per_func[name] = d
            cost += d
        for name in added:
            c = float(node_count(b.funcs[name]))
            per_func[name] = c
            cost += c
        for name in removed:
            c = float(node_count(a.funcs[name]))
            per_func[name] = c
            cost += c
    else:
        added, removed = [], []
        if a.ir is not None and b.ir is not None:
            cost, degraded = layered_distance(a.ir, b.ir, max_nodes=max_nodes)
        elif b.ir is not None:
            cost = float(node_count(b.ir))
        elif a.ir is not None:
            cost = float(node_count(a.ir))

    denom = max(a.total_nodes, b.total_nodes)
    dsem = cost / (denom + 1.0) if denom > 0 else (1.0 if cost > 0 else 0.0)
    return EvolutionEdge(
        from_id=a.snapshot_id,
        to_id=b.snapshot_id,
        ts=b.ts,
        dsem=round(min(dsem, 1.0), 4),
        raw_cost=round(cost, 3),
        degraded=degraded,
        from_empty=(a.total_nodes == 0),
        per_func={k: round(v, 3) for k, v in per_func.items()},
        added=added,
        removed=removed,
    )


def build_evolution(snapshots: list[Snapshot], max_nodes: int = DEFAULT_MAX_NODES) -> list[EvolutionEdge]:
    edges: list[EvolutionEdge] = []
    for prev, cur in zip(snapshots, snapshots[1:]):
        edges.append(_diff_snapshots(prev, cur, max_nodes))
    return edges


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2 == 1:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round((len(s) - 1) * q))))
    return float(s[idx])


def mutation_points(edges: list[EvolutionEdge], factor: float = 3.0, min_abs: float = 0.35) -> list[EvolutionEdge]:
    """语义突变点：显著高于本会话自身中位数的编辑。"""
    if not edges:
        return []
    med = median([e.dsem for e in edges])
    threshold = max(min_abs, factor * med)
    return [e for e in edges if e.dsem >= threshold]
