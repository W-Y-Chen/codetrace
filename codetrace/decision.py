"""证据融合与三档分级结论（方案 §3.1.4）。

**架构层硬约束**：系统任何返回路径都不得产出二元"原创性/作弊"判定结论。
该约束由 Verdict.validate() 与 tests/test_decision.py 双重保证。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .channels import ChannelScore, Evidence

LEVEL_NONE = "无异常"
LEVEL_WATCH = "建议关注"
LEVEL_REVIEW = "需复核"

LEVEL_CODES = {LEVEL_NONE: "none", LEVEL_WATCH: "watch", LEVEL_REVIEW: "review"}

STRONG_THRESHOLD = 0.66
WEAK_THRESHOLD = 0.33

# 触发"需复核"的强信号通道：粘入比例与语义突变任一达强信号即触发
VETO_CHANNELS = ("P1", "P2")

FORBIDDEN_FIELDS = {"is_cheating", "cheating", "ai_generated", "plagiarism", "is_plagiarized"}


@dataclass
class Verdict:
    level: str
    level_code: str
    reason: str
    strong_channels: list[str] = field(default_factory=list)
    weak_channels: list[str] = field(default_factory=list)
    highlights: list[Evidence] = field(default_factory=list)
    integrity_score: int = 100

    def validate(self) -> None:
        if self.level not in LEVEL_CODES:
            raise ValueError(f"未知结论档位: {self.level}")
        for name in FORBIDDEN_FIELDS:
            if hasattr(self, name):
                raise AssertionError(f"Verdict 禁止包含二元判定字段: {name}")

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "level_code": self.level_code,
            "reason": self.reason,
            "strong_channels": self.strong_channels,
            "weak_channels": self.weak_channels,
            "highlights": [e.to_dict() for e in self.highlights],
            "integrity_score": self.integrity_score,
            "disclaimer": "本结果为过程证据摘要，不构成原创性判定结论，最终判定由教师作出。",
        }


def decide(
    scores: dict[str, ChannelScore],
    strong: float = STRONG_THRESHOLD,
    weak: float = WEAK_THRESHOLD,
) -> Verdict:
    enabled = {k: v for k, v in scores.items() if v.enabled}
    strong_ch = sorted(k for k, v in enabled.items() if v.score >= strong)
    weak_ch = sorted(k for k, v in enabled.items() if weak <= v.score < strong)

    all_ev: list[Evidence] = []
    for v in enabled.values():
        all_ev.extend(v.evidences)

    if len(strong_ch) >= 2 or any(c in strong_ch for c in VETO_CHANNELS):
        level = LEVEL_REVIEW
        k = 5
        reason = (
            f"强信号通道 {strong_ch}；" if strong_ch else ""
        ) + "证据片段已高亮，需教师人工复核（系统不作原创性结论）"
    elif weak_ch:
        level = LEVEL_WATCH
        k = 3
        reason = f"通道 {weak_ch} 存在轻度偏离，建议关注；不推送复核"
    else:
        level = LEVEL_NONE
        k = 0
        reason = "各通道均在基线范围内，未发现过程异常"

    highlights = sorted(all_ev, key=lambda e: e.score, reverse=True)[:k]

    values = [v.score for v in enabled.values()] or [0.0]
    integrity = int(round(100 * (1 - sum(values) / len(values))))

    verdict = Verdict(
        level=level,
        level_code=LEVEL_CODES[level],
        reason=reason,
        strong_channels=strong_ch,
        weak_channels=weak_ch,
        highlights=highlights,
        integrity_score=integrity,
    )
    verdict.validate()
    return verdict


def summarize(scores: dict[str, ChannelScore]) -> dict:
    return {k: v.to_dict() for k, v in scores.items()}
