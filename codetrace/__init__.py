"""CodeTrace 码迹 —— 编程过程性证据分析原型 v0.1。

零第三方依赖（仅 Python 标准库），可在任意 Python 3.9+ 环境直接运行。
"""
from __future__ import annotations

__version__ = "0.1.0"

from .events import Session, EditEvent, RunEvent, SnapshotEvent, parse_event, to_dict
from .pipeline import analyze, analyze_events, reverify

__all__ = [
    "__version__",
    "Session",
    "EditEvent",
    "RunEvent",
    "SnapshotEvent",
    "parse_event",
    "to_dict",
    "analyze",
    "analyze_events",
    "reverify",
]
