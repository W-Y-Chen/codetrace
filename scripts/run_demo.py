"""一键演示：跑通四个剧本并打印结果。

用法：python scripts/run_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codetrace.pipeline import analyze, reverify  # noqa: E402
from codetrace.simulate import PROBLEM, SCENARIOS  # noqa: E402


def bar(score: float, width: int = 20) -> str:
    filled = int(round(score * width))
    return "[" + "#" * filled + "." * (width - filled) + f"] {score:.2f}"


def main() -> int:
    print("=" * 78)
    print("CodeTrace 码迹 v0.1 —— 四种典型编程过程的过程性证据分析")
    print("题目:", PROBLEM["statement"])
    print("=" * 78)

    for key, (label, fn) in SCENARIOS.items():
        session = fn()
        result = analyze(session, problem=PROBLEM)
        v = result["verdict"]
        print(f"\n■ {label}   session={result['session_id']}  student={result['student_id']}")
        print(f"  基线来源: {result['baseline_source']}")
        print(f"  结论档位: {v['level']}  (过程完整度 {v['integrity_score']}/100)")
        print(f"  判定依据: {v['reason']}")
        print("  通道分值:")
        for name, ch in result["channels"].items():
            flag = "" if ch["enabled"] else "  (已禁用)"
            print(f"    {name} {bar(ch['score'])}{flag}  证据 {len(ch['evidences'])} 条")
        print("  过程特征:")
        f = result["features"]
        print(
            f"    编辑 {f['n_edits']} 次 | 运行 {f['n_runs']} 次 | 快照 {f['n_snapshots']} 个 | "
            f"粘贴占比 {f['paste_ratio']:.0%} | 最大单次粘贴 {f['max_paste_burst']} 字符"
        )
        print(
            f"    最大语义变化 {f['max_dsem']:.2f} | 突变点 {f['mutation_count']} 个 | "
            f"调试密度 {f['debug_density']:.1f}/100 | 风格漂移 {f['style_drift']:.2f}"
        )
        if v["highlights"]:
            print("  高亮证据片段:")
            for h in v["highlights"]:
                loc = h["loc"] or "-"
                print(f"    - [{h['channel']}] {h['kind']} @ {loc}: {h['detail']}")
        pkg = reverify(result["package"])
        print(f"  证据包离线校验: {'通过' if pkg['ok'] else '失败 ' + pkg['reason']}  "
              f"(链头 {result['chain_head'][:12]}…)")
        print(f"  说明: {v['disclaimer']}")

    print("\n" + "=" * 78)
    print("注：以上为模拟数据的原型验证结果，不是真实评测指标。")
    print("真实指标须按方案 §8 采集对照数据集后实测，未实测不得对外发布。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
