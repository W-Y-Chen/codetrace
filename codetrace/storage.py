"""SQLite 持久化（标准库 sqlite3，零依赖）。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    student_id TEXT,
    problem_id TEXT,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    seq INTEGER,
    kind TEXT,
    payload TEXT,
    chain_hash TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    session_id TEXT PRIMARY KEY,
    result_json TEXT,
    package_json TEXT,
    created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
"""


class Store:
    def __init__(self, path: str = "data/codetrace.db"):
        self.path = path
        p = Path(path)
        if p.parent and not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def save_session(self, session: Any, hashes: Optional[list[str]] = None) -> None:
        from .events import to_dict

        self.conn.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)",
            (session.session_id, getattr(session, "student_id", ""), getattr(session, "problem_id", ""), int(time.time())),
        )
        self.conn.execute("DELETE FROM events WHERE session_id=?", (session.session_id,))
        for i, ev in enumerate(session.sorted_events()):
            self.conn.execute(
                "INSERT INTO events (session_id, seq, kind, payload, chain_hash) VALUES (?,?,?,?,?)",
                (
                    session.session_id,
                    i,
                    getattr(ev, "kind", ""),
                    json.dumps(to_dict(ev), ensure_ascii=False),
                    hashes[i] if hashes and i < len(hashes) else "",
                ),
            )
        self.conn.commit()

    def save_report(self, session_id: str, result: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO reports VALUES (?,?,?,?)",
            (session_id, json.dumps(result, ensure_ascii=False), result.get("package", ""), int(time.time())),
        )
        self.conn.commit()

    def list_sessions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.session_id, s.student_id, s.problem_id, s.created_at,"
            " (SELECT COUNT(*) FROM events e WHERE e.session_id=s.session_id) AS n_events"
            " FROM sessions s ORDER BY s.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def load_events(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT payload FROM events WHERE session_id=? ORDER BY seq", (session_id,)
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def load_report(self, session_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT result_json FROM reports WHERE session_id=?", (session_id,)).fetchone()
        return json.loads(row["result_json"]) if row else None

    def load_package(self, session_id: str) -> Optional[str]:
        row = self.conn.execute("SELECT package_json FROM reports WHERE session_id=?", (session_id,)).fetchone()
        return row["package_json"] if row else None

    def close(self) -> None:
        self.conn.close()
