"""五通道证据打分（方案 §3.1.3）。

P1 粘入比例    —— 客观事实通道，使用绝对阈值（不依赖个体基线）
P2 语义突变    —— 相对通道，与学生自身历史的 Δsem 中位数比较
P3 调试循环    —— 相对通道，运行失败→修复循环密度
P4 风格漂移    —— 客观通道，同一次作业内前后半程风格分布距离
P5 需求一致性  —— 词法近似版（语义版需句向量模型，列为可选模块）

诚实说明：P5 当前为词法近似实现，未使用语义向量模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .astutil import identifier_tokens, style_features
from .baseline import Baseline
from .evolution import EvolutionEdge, Snapshot, median, mutation_points
from .events import Session

LARGE_PASTE_CHARS = 120
BURST_FULL = 400.0
PASTE_RATIO_FULL = 0.35


@dataclass
class Evidence:
    channel: str
    kind: str
    ts: int
    loc: str = ""
    detail: str = ""
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "kind": self.kind,
            "ts": self.ts,
            "loc": self.loc,
            "detail": self.detail,
            "score": round(self.score, 4),
        }


@dataclass
class ChannelScore:
    channel: str
    score: float
    enabled: bool = True
    evidences: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "score": round(self.score, 4),
            "enabled": self.enabled,
            "evidences": [e.to_dict() for e in self.evidences],
        }


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------- 特征提取 ----------------

def extract_features(session: Session, snapshots: list[Snapshot], edges: list[EvolutionEdge]) -> dict:
    edits = session.edits()
    runs = session.runs()

    inserted = sum(e.text_len for e in edits if e.op in ("insert", "replace", "paste"))
    pasted = sum(e.paste_len for e in edits)
    paste_ratio = pasted / inserted if inserted else 0.0
    max_burst = max((e.paste_len for e in edits), default=0)

    scored_edges = [e for e in edges if not e.from_empty]
    dsems = [e.dsem for e in scored_edges] or [0.0]
    mutations = mutation_points(scored_edges)

    fail_runs = [r for r in runs if r.result in ("fail", "error")]
    debug_density = (len(fail_runs) / len(edits) * 100.0) if edits else 0.0

    drift = style_drift(snapshots)

    return {
        "n_edits": len(edits),
        "n_runs": len(runs),
        "n_snapshots": len(snapshots),
        "paste_ratio": round(paste_ratio, 4),
        "max_paste_burst": max_burst,
        "max_dsem": round(max(dsems), 4),
        "median_dsem": round(median(dsems), 4),
        "mutation_count": len(mutations),
        "debug_density": round(debug_density, 4),
        "style_drift": round(drift, 4),
    }


def style_drift(snapshots: list[Snapshot]) -> float:
    """前后半程风格特征的 L1 距离。"""
    usable = [s for s in snapshots if s.code.strip()]
    if len(usable) < 4:
        return 0.0
    half = len(usable) // 2
    early = _agg_style(usable[:half])
    late = _agg_style(usable[half:])
    keys = ["multiword_snake", "multiword_camel", "comment_density"]
    dist = sum(abs(early[k] - late[k]) for k in keys)
    dist += abs(early["avg_ident_len"] - late["avg_ident_len"]) / 12.0
    return dist


def _agg_style(snaps: list[Snapshot]) -> dict:
    acc = {
        "multiword_snake": 0.0,
        "multiword_camel": 0.0,
        "comment_density": 0.0,
        "avg_ident_len": 0.0,
    }
    if not snaps:
        return acc
    for s in snaps:
        f = style_features(s.code)
        for k in acc:
            acc[k] += f[k] / len(snaps)
    return acc


# ---------------- 通道打分 ----------------

def score_p1(session: Session, features: dict, edges: list[EvolutionEdge]) -> ChannelScore:
    ev = []
    for e in session.edits():
        if e.paste_len >= LARGE_PASTE_CHARS:
            ev.append(
                Evidence(
                    channel="P1",
                    kind="large_paste",
                    ts=e.ts,
                    loc=e.file_id,
                    detail=f"单次粘贴 {e.paste_len} 字符（阈值 {LARGE_PASTE_CHARS}）",
                    score=_clamp01(e.paste_len / BURST_FULL),
                )
            )
    ratio_part = _clamp01(features["paste_ratio"] / PASTE_RATIO_FULL)
    burst_part = _clamp01(features["max_paste_burst"] / BURST_FULL)
    score = min(1.0, 0.6 * ratio_part + 0.4 * burst_part)

    # 归因：把大块粘贴定位到受影响的函数
    if ev and edges:
        top = max(ev, key=lambda x: x.score)
        near = min(edges, key=lambda e: abs(e.ts - top.ts))
        if near.per_func:
            name = max(near.per_func, key=near.per_func.get)
            top.loc = f"{top.loc}::{name}"
            top.detail += f"，受影响最大的函数: {name}"
    return ChannelScore("P1", round(score, 4), True, ev)


def score_p2(features: dict, baseline: Baseline) -> ChannelScore:
    dev = baseline.dev("max_dsem", features["max_dsem"])
    base = _clamp01(dev / 2.5)
    mut = _clamp01(features["mutation_count"] / 3.0)
    score = min(1.0, 0.75 * base + 0.25 * mut)
    ev = []
    if base > 0.1:
        ev.append(
            Evidence(
                channel="P2",
                kind="semantic_mutation",
                ts=0,
                loc="",
                detail=(
                    f"最大语义变化量 {features['max_dsem']}，"
                    f"高于自身基线中位数 {baseline.median.get('max_dsem', 0)}"
                ),
                score=round(base, 4),
            )
        )
    if features["mutation_count"]:
        ev.append(
            Evidence(
                channel="P2",
                kind="mutation_points",
                ts=0,
                loc="",
                detail=f"检出 {features['mutation_count']} 个语义突变点",
                score=round(mut, 4),
            )
        )
    return ChannelScore("P2", round(score, 4), True, ev)


def score_p3(session: Session, features: dict, baseline: Baseline) -> ChannelScore:
    ev = []
    if features["n_runs"] == 0:
        score = 0.45 if features["n_edits"] >= 5 else 0.0
        if score:
            ev.append(
                Evidence(
                    channel="P3",
                    kind="no_debug_record",
                    ts=0,
                    loc="",
                    detail="全程无运行/调试记录（本通道弱信号，需结合其它通道）",
                    score=score,
                )
            )
        return ChannelScore("P3", round(score, 4), True, ev)

    dev = baseline.dev("debug_density", features["debug_density"])
    inverse = -dev
    score = _clamp01(inverse / 2.5)
    if score > 0.1:
        ev.append(
            Evidence(
                channel="P3",
                kind="debug_cycle_sparse",
                ts=0,
                loc="",
                detail=(
                    f"调试循环密度 {features['debug_density']}/100 次编辑，"
                    f"低于自身基线 {baseline.median.get('debug_density', 0)}"
                ),
                score=round(score, 4),
            )
        )
    return ChannelScore("P3", round(score, 4), True, ev)


def score_p4(features: dict, baseline: Baseline) -> ChannelScore:
    dev = baseline.dev("style_drift", features["style_drift"])
    absolute = _clamp01(features["style_drift"] / 0.6)
    score = min(1.0, max(absolute, _clamp01(dev / 2.5)))
    ev = []
    if absolute > 0.15:
        ev.append(
            Evidence(
                channel="P4",
                kind="style_drift",
                ts=0,
                loc="",
                detail=f"作业前后半程风格分布距离 {features['style_drift']}",
                score=round(absolute, 4),
            )
        )
    return ChannelScore("P4", round(score, 4), True, ev)


def score_p5(snapshots: list[Snapshot], problem: Optional[dict]) -> ChannelScore:
    """需求—代码一致性（词法近似版）。未提供题目关键词时禁用本通道。"""
    if not problem or not problem.get("keywords"):
        return ChannelScore("P5", 0.0, False, [])
    code = "\n".join(s.code for s in snapshots)
    if not code.strip():
        return ChannelScore("P5", 0.0, True, [])

    keywords = [k.lower() for k in problem["keywords"]]
    tokens = {_stem(t.lower()) for t in identifier_tokens(code)}
    tokens |= {_stem(t.lower()) for t in _comment_tokens(code)}
    hit = sum(1 for k in keywords if _stem(k) in tokens)
    overlap = hit / len(keywords)
    score = _clamp01((0.30 - overlap) / 0.30)
    ev = []
    if score > 0.05:
        ev.append(
            Evidence(
                channel="P5",
                kind="requirement_mismatch",
                ts=0,
                loc="",
                detail=f"题目关键词命中率 {overlap:.2%}（{hit}/{len(keywords)}）",
                score=round(score, 4),
            )
        )
    return ChannelScore("P5", round(score, 4), True, ev)


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("s"):
        return word[:-1]
    return word


def _comment_tokens(code: str) -> list[str]:
    out = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            out.extend(t for t in stripped.lstrip("#").split())
    return out


def score_all(
    session: Session,
    snapshots: list[Snapshot],
    edges: list[EvolutionEdge],
    baseline: Baseline,
    problem: Optional[dict] = None,
) -> tuple[dict[str, ChannelScore], dict]:
    features = extract_features(session, snapshots, edges)
    scores = {
        "P1": score_p1(session, features, edges),
        "P2": score_p2(features, baseline),
        "P3": score_p3(session, features, baseline),
        "P4": score_p4(features, baseline),
        "P5": score_p5(snapshots, problem),
    }
    return scores, features
