"""结构化过程事件模型。

设计约束（对应方案 §3.1.1）：
- 采集端只产出结构化事件，代码正文仅存在于 SnapshotEvent.code 中；
- privacy_mode=True 时上传前调用 strip_code() 移除代码正文，只保留 AST 摘要；
- canonical_json 保证同一事件在不同平台上的字节表示完全一致，是哈希链可校验的前提。
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

EDIT_OPS = ("insert", "delete", "replace", "paste", "undo", "redo", "save")
RUN_KINDS = ("run", "test", "build")
RUN_RESULTS = ("pass", "fail", "error")


def _json_default(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    raise TypeError(f"无法序列化的类型: {type(o).__name__}")


def canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(text: str) -> str:
    return sha256_hex(text.encode("utf-8"))[:16]


@dataclass
class EditEvent:
    ts: int
    session_id: str
    file_id: str = "main.py"
    op: str = "insert"
    range_start: int = 0
    range_end: int = 0
    text_len: int = 0
    paste_len: int = 0
    clipboard_hash: str = ""
    snapshot_id: str = ""
    kind: str = "edit"

    def __post_init__(self) -> None:
        if self.op not in EDIT_OPS:
            raise ValueError(f"未知编辑操作: {self.op}")


@dataclass
class RunEvent:
    ts: int
    session_id: str
    result: str = "pass"
    error_type: str = ""
    error_loc: str = ""
    next_fix_ms: Optional[int] = None
    kind: str = "run"

    def __post_init__(self) -> None:
        if self.result not in RUN_RESULTS:
            raise ValueError(f"未知运行结果: {self.result}")


@dataclass
class SnapshotEvent:
    ts: int
    session_id: str
    snapshot_id: str = ""
    ast_hash: str = ""
    code: str = ""
    kind: str = "snapshot"


EVENT_TYPES = {
    "edit": EditEvent,
    "run": RunEvent,
    "snapshot": SnapshotEvent,
}


def to_dict(event: Any) -> dict:
    return asdict(event)


def parse_event(raw: dict) -> Any:
    kind = raw.get("kind")
    cls = EVENT_TYPES.get(kind)
    if cls is None:
        raise ValueError(f"未知事件类型: {kind}")
    names = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in raw.items() if k in names})


def strip_code(event: Any) -> Any:
    """隐私模式：移除代码正文，只保留结构摘要。"""
    if isinstance(event, SnapshotEvent):
        stripped = SnapshotEvent(
            ts=event.ts,
            session_id=event.session_id,
            snapshot_id=event.snapshot_id,
            ast_hash=event.ast_hash,
            code="",
        )
        return stripped
    return event


def strip_code_all(events: list) -> list:
    return [strip_code(e) for e in events]


@dataclass
class Session:
    session_id: str
    student_id: str
    problem_id: str = ""
    events: list = field(default_factory=list)

    def sorted_events(self) -> list:
        return sorted(self.events, key=lambda e: (e.ts, getattr(e, "kind", "")))

    def snapshots(self) -> list[SnapshotEvent]:
        return [e for e in self.sorted_events() if isinstance(e, SnapshotEvent)]

    def edits(self) -> list[EditEvent]:
        return [e for e in self.sorted_events() if isinstance(e, EditEvent)]

    def runs(self) -> list[RunEvent]:
        return [e for e in self.sorted_events() if isinstance(e, RunEvent)]
