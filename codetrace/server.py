"""零依赖 HTTP 服务（标准库 http.server）。

接口：
  GET  /api/health
  GET  /api/demo                      四种典型过程的分析结果
  GET  /api/sessions                  已保存会话列表
  GET  /api/sessions/{id}/report      分析报告
  GET  /api/sessions/{id}/package     证据包
  POST /api/analyze                   即时分析（body: {session_id, events, ...}）
  POST /api/sessions                  保存并分析
  POST /api/verify                    离线校验证据包
  GET  /                              演示页面
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from . import chain
from .events import Session, parse_event
from .pipeline import analyze, reverify
from .simulate import PROBLEM
from .storage import Store

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class AppState:
    def __init__(self, db_path: str = "data/codetrace.db"):
        self.store = Store(db_path)
        self.lock = threading.Lock()


def _json(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html(handler: BaseHTTPRequestHandler, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _events_from_raw(raw_events: list) -> list:
    return [parse_event(e) for e in raw_events]


def _run_analysis(payload: dict) -> dict:
    session_id = payload.get("session_id") or "adhoc"
    student_id = payload.get("student_id", "")
    problem_id = payload.get("problem_id", "p001")
    events = _events_from_raw(payload.get("events", []))
    history = payload.get("history") or None
    problem = payload.get("problem") or PROBLEM
    session = Session(
        session_id=session_id, student_id=student_id, problem_id=problem_id, events=events
    )
    return analyze(session, history=history, problem=problem)


def handle_get(handler: BaseHTTPRequestHandler, state: AppState, path: str) -> bool:
    if path in ("/", "/index.html"):
        index = WEB_DIR / "index.html"
        if index.exists():
            _html(handler, index.read_text(encoding="utf-8"))
        else:
            _html(handler, "<h1>CodeTrace</h1><p>web/index.html 缺失</p>")
        return True

    if path == "/api/health":
        _json(handler, 200, {"ok": True, "version": "0.1.0"})
        return True

    if path == "/api/demo":
        from .simulate import SCENARIOS

        out = []
        for key, (label, fn) in SCENARIOS.items():
            result = analyze(fn(), problem=PROBLEM)
            out.append(
                {
                    "key": key,
                    "label": label,
                    "verdict": result["verdict"],
                    "features": result["features"],
                    "channels": {
                        k: {"score": v["score"], "enabled": v["enabled"], "n_evidence": len(v["evidences"])}
                        for k, v in result["channels"].items()
                    },
                    "session_id": result["session_id"],
                }
            )
        _json(handler, 200, {"items": out})
        return True

    if path.startswith("/api/demo/"):
        from .simulate import SCENARIOS

        key = path[len("/api/demo/") :]
        if key not in SCENARIOS:
            _json(handler, 404, {"error": f"未知剧本 {key}"})
            return True
        result = analyze(SCENARIOS[key][1](), problem=PROBLEM)
        _json(handler, 200, result)
        return True

    if path == "/api/sessions":
        _json(handler, 200, {"items": state.store.list_sessions()})
        return True

    if path.startswith("/api/sessions/") and path.endswith("/report"):
        sid = path[len("/api/sessions/") : -len("/report")]
        report = state.store.load_report(sid)
        if report is None:
            _json(handler, 404, {"error": "未找到报告"})
        else:
            _json(handler, 200, report)
        return True

    if path.startswith("/api/sessions/") and path.endswith("/package"):
        sid = path[len("/api/sessions/") : -len("/package")]
        pkg = state.store.load_package(sid)
        if pkg is None:
            _json(handler, 404, {"error": "未找到证据包"})
        else:
            _json(handler, 200, {"package": pkg})
        return True

    return False


def handle_post(handler: BaseHTTPRequestHandler, state: AppState, path: str, payload: dict) -> bool:
    if path == "/api/analyze":
        _json(handler, 200, _run_analysis(payload))
        return True

    if path == "/api/sessions":
        result = _run_analysis(payload)
        with state.lock:
            state.store.save_report(result["session_id"], result)
        _json(handler, 200, result)
        return True

    if path == "/api/verify":
        pkg_text = payload.get("package")
        if isinstance(pkg_text, dict):
            pkg_text = json.dumps(pkg_text, ensure_ascii=False)
        if not pkg_text:
            _json(handler, 400, {"error": "缺少 package 字段"})
        else:
            _json(handler, 200, reverify(pkg_text))
        return True

    return False


def make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # 精简日志
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if not handle_get(self, state, path):
                _json(self, 404, {"error": f"未知路径 {path}"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                _json(self, 400, {"error": "请求体不是合法 JSON"})
                return
            try:
                if not handle_post(self, state, path, payload):
                    _json(self, 404, {"error": f"未知路径 {path}"})
            except Exception as exc:  # noqa: BLE001
                _json(self, 500, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, db_path: str = "data/codetrace.db") -> None:
    state = AppState(db_path)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"CodeTrace 服务已启动: http://{host}:{port}")
    print("按 Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="CodeTrace 演示服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default="data/codetrace.db")
    args = parser.parse_args()
    serve(args.host, args.port, args.db)


if __name__ == "__main__":
    main()
