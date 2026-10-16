"""自适应基线（方案 §3.1.3）。

以**学生自身历史统计量**为基线，避免"写得快=作弊"的系统性偏差。
历史样本不足时回退到全局保守基线（冷启动）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .evolution import median, quantile

MIN_HISTORY = 3

# 全局保守基线：仅在历史样本不足时使用。取值来自设计假设，
# 必须用实测数据（方案 §8）重新标定后方可用于正式评估。
GLOBAL_BASELINE: dict[str, tuple[float, float]] = {
    "max_dsem": (0.45, 0.25),
    "median_dsem": (0.20, 0.15),
    "debug_density": (3.0, 2.0),
    "style_drift": (0.12, 0.10),
    "paste_ratio": (0.05, 0.08),
}


@dataclass
class Baseline:
    source: str
    median: dict[str, float] = field(default_factory=dict)
    iqr: dict[str, float] = field(default_factory=dict)

    def dev(self, key: str, value: float, eps: float = 0.05) -> float:
        """标准化偏离度：正值表示高于自身历史水平。"""
        med = self.median.get(key, 0.0)
        spread = self.iqr.get(key, 0.0)
        return (value - med) / (spread + eps)


def build_baseline(history: Optional[list[dict]]) -> Baseline:
    """history: 同一学生历史会话的特征字典列表。"""
    if not history or len(history) < MIN_HISTORY:
        med = {k: v[0] for k, v in GLOBAL_BASELINE.items()}
        iqr = {k: v[1] for k, v in GLOBAL_BASELINE.items()}
        return Baseline(source="global(cold-start)", median=med, iqr=iqr)

    keys = set()
    for item in history:
        keys.update(item.keys())
    med, iqr = {}, {}
    for key in sorted(keys):
        values = [float(h.get(key, 0.0)) for h in history]
        med[key] = median(values)
        iqr[key] = max(quantile(values, 0.75) - quantile(values, 0.25), 0.0)
    return Baseline(source=f"student(n={len(history)})", median=med, iqr=iqr)
