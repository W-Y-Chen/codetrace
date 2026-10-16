"""生成样例事件文件到 data/samples/，供离线演示与回归使用。

用法：python scripts/gen_samples.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codetrace.events import to_dict  # noqa: E402
from codetrace.simulate import SCENARIOS  # noqa: E402

OUT = ROOT / "data" / "samples"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, (label, fn) in SCENARIOS.items():
        session = fn()
        payload = {
            "session_id": session.session_id,
            "student_id": session.student_id,
            "problem_id": session.problem_id,
            "label": label,
            "events": [to_dict(e) for e in session.sorted_events()],
        }
        path = OUT / f"{key}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已生成 {path}  ({len(payload['events'])} 个事件)  {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
