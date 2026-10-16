"""端到端分析流水线：事件流 -> 演化图 -> 五通道 -> 分级结论 -> 证据包。"""
from __future__ import annotations

from typing import Optional

from . import chain
from .astutil import ir_hash
from .baseline import build_baseline
from .channels import score_all
from .decision import decide, summarize
from .evolution import build_evolution, make_snapshot
from .events import Session, SnapshotEvent, parse_event
from .ted import DEFAULT_MAX_NODES


def analyze(
    session: Session,
    history: Optional[list[dict]] = None,
    problem: Optional[dict] = None,
    max_nodes: int = DEFAULT_MAX_NODES,
    batch_size: int = 32,
    with_package: bool = True,
) -> dict:
    snapshots = [make_snapshot(e) for e in session.snapshots()]
    edges = build_evolution(snapshots, max_nodes=max_nodes)
    baseline = build_baseline(history)
    scores, features = score_all(session, snapshots, edges, baseline, problem)
    verdict = decide(scores)

    unparsed = [s.snapshot_id for s in snapshots if not s.parse_ok]
    degraded_edges = sum(1 for e in edges if e.degraded)

    result = {
        "session_id": session.session_id,
        "student_id": getattr(session, "student_id", ""),
        "problem_id": getattr(session, "problem_id", ""),
        "baseline_source": baseline.source,
        "features": features,
        "channels": summarize(scores),
        "verdict": verdict.to_dict(),
        "evolution": [
            {
                "from": e.from_id,
                "to": e.to_id,
                "ts": e.ts,
                "dsem": e.dsem,
                "degraded": e.degraded,
                "from_empty": e.from_empty,
                "per_func": e.per_func,
            }
            for e in edges
        ],
        "diagnostics": {
            "snapshots": len(snapshots),
            "unparsed_snapshots": len(unparsed),
            "degraded_edges": degraded_edges,
            "ast_hashes": [ir_hash(s.ir)[:12] for s in snapshots if s.ir is not None],
        },
    }

    if with_package:
        pkg = chain.build_package(session, result, batch_size=batch_size)
        result["package"] = pkg.to_json()
        result["chain_head"] = pkg.hashes[-1] if pkg.hashes else ""
    return result


def analyze_events(
    events: list,
    session_id: str,
    student_id: str = "",
    problem_id: str = "",
    **kwargs,
) -> dict:
    parsed = [parse_event(e) if isinstance(e, dict) else e for e in events]
    session = Session(session_id=session_id, student_id=student_id, problem_id=problem_id, events=parsed)
    return analyze(session, **kwargs)


def reverify(package_json: str) -> dict:
    """离线校验证据包（不需要原系统在线）。"""
    pkg = chain.EvidencePackage.from_json(package_json)
    return chain.verify_package(pkg)
