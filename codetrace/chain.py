"""链式存证与证据包（方案 §3.2，创新二）。

- 链式摘要：h_i = SHA256(h_{i-1} || canonical_json(event_i))
- 增量 Merkle：每 batch_size 条事件成一批，批内构建 Merkle 树，根锚定外部时间戳
- 证据包：自包含，可离线独立校验
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .events import canonical_json, sha256_hex

CHAIN_VERSION = "codetrace-chain-v1"


def chain_seed(session_id: str, nonce: str = "") -> str:
    return sha256_hex(f"{CHAIN_VERSION}|{session_id}|{nonce}".encode("utf-8"))


def compute_chain(events: list, seed: str) -> list[str]:
    """按时间序递归计算链式摘要。"""
    prev = seed
    out = []
    for ev in events:
        blob = prev.encode("utf-8") + b"||" + canonical_json(ev)
        prev = sha256_hex(blob)
        out.append(prev)
    return out


def verify_chain(events: list, hashes: list[str], seed: str) -> tuple[bool, Optional[int]]:
    """重算并比对。返回 (是否一致, 首个不一致位置)。"""
    if len(events) != len(hashes):
        return False, min(len(events), len(hashes))
    expected = compute_chain(events, seed)
    for i, (a, b) in enumerate(zip(expected, hashes)):
        if a != b:
            return False, i
    return True, None


# ---------------- Merkle ----------------

def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return ""
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            sha256_hex((level[i] + level[i + 1]).encode("utf-8"))
            for i in range(0, len(level), 2)
        ]
    return level[0]


@dataclass
class Batch:
    index: int
    start: int
    end: int
    root: str
    anchor: str = ""
    anchored_at: int = 0


def build_batches(hashes: list[str], batch_size: int = 32, anchor_ts: Optional[int] = None) -> list[Batch]:
    """按批构建增量 Merkle 树；batch_size 可根据事件速率自适应（此处为固定值）。"""
    batches: list[Batch] = []
    ts = anchor_ts if anchor_ts is not None else int(time.time())
    for i, start in enumerate(range(0, len(hashes), batch_size)):
        chunk = hashes[start : start + batch_size]
        root = merkle_root(chunk)
        anchor = sha256_hex((root + str(ts)).encode("utf-8"))
        batches.append(
            Batch(index=i, start=start, end=start + len(chunk), root=root, anchor=anchor, anchored_at=ts)
        )
    return batches


# ---------------- 证据包 ----------------

@dataclass
class EvidencePackage:
    version: str = "codetrace-package-v1"
    session_id: str = ""
    student_id: str = ""
    problem_id: str = ""
    seed: str = ""
    events: list = field(default_factory=list)
    hashes: list[str] = field(default_factory=list)
    batches: list = field(default_factory=list)
    analysis: dict = field(default_factory=dict)
    created_at: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "session_id": self.session_id,
                "student_id": self.student_id,
                "problem_id": self.problem_id,
                "seed": self.seed,
                "events": self.events,
                "hashes": self.hashes,
                "batches": [b.__dict__ for b in self.batches],
                "analysis": self.analysis,
                "created_at": self.created_at,
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "EvidencePackage":
        raw = json.loads(text)
        pkg = cls(
            version=raw.get("version", ""),
            session_id=raw.get("session_id", ""),
            student_id=raw.get("student_id", ""),
            problem_id=raw.get("problem_id", ""),
            seed=raw.get("seed", ""),
            events=raw.get("events", []),
            hashes=raw.get("hashes", []),
            analysis=raw.get("analysis", {}),
            created_at=raw.get("created_at", 0),
        )
        pkg.batches = [Batch(**b) for b in raw.get("batches", [])]
        return pkg


def verify_package(pkg: EvidencePackage) -> dict:
    """离线独立校验：不依赖原系统任何外部服务。"""
    from .events import parse_event

    try:
        events = [parse_event(e) for e in pkg.events]
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"事件解析失败: {exc}", "first_bad_index": None}

    ok, bad = verify_chain(events, pkg.hashes, pkg.seed)
    result = {
        "ok": ok,
        "chain_ok": ok,
        "first_bad_index": bad,
        "batches_ok": True,
        "bad_batches": [],
        "reason": "",
    }
    if not ok:
        result["reason"] = f"链式摘要在第 {bad} 条事件处不一致"

    for b in pkg.batches:
        chunk = pkg.hashes[b.start : b.end]
        if merkle_root(chunk) != b.root:
            result["batches_ok"] = False
            result["bad_batches"].append(b.index)
    if not result["batches_ok"]:
        result["ok"] = False
        result["reason"] = (result["reason"] + f"；Merkle 根不匹配的批次: {result['bad_batches']}").strip("；")
    return result


def build_package(session: Any, analysis: dict, batch_size: int = 32, nonce: str = "") -> EvidencePackage:
    from .events import to_dict

    events = session.sorted_events()
    seed = chain_seed(session.session_id, nonce)
    hashes = compute_chain(events, seed)
    batches = build_batches(hashes, batch_size=batch_size)
    return EvidencePackage(
        session_id=session.session_id,
        student_id=getattr(session, "student_id", ""),
        problem_id=getattr(session, "problem_id", ""),
        seed=seed,
        events=[to_dict(e) for e in events],
        hashes=hashes,
        batches=batches,
        analysis=analysis,
        created_at=int(time.time()),
    )
