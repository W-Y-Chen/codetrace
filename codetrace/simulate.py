"""过程模拟器：生成四种典型编程过程的事件流。

用途：
1. 无需真实学生即可端到端验证流水线（对应方案 §11.4 的演示数据准备）；
2. 为回归测试提供确定性输入；
3. 演示剧本 1/2/3/4 的数据来源。

诚实说明：模拟数据用于验证系统链路与指标口径，**不能替代 §8 的真实对照数据集**。
"""
from __future__ import annotations

import random
from typing import Optional

from .events import EditEvent, RunEvent, Session, SnapshotEvent, short_hash

PROBLEM = {
    "problem_id": "p001",
    "title": "词频排序",
    "statement": "统计列表中每个元素出现次数，按出现次数降序、次数相同时按元素升序排列，返回排序后的元素列表。",
    "keywords": ["count", "sort", "desc", "asc", "frequency", "element", "list", "items", "top"],
}

CHUNKS = [
    "def count_items(items):\n    counts = {}\n    for it in items:\n        counts[it] = counts.get(it, 0) + 1\n    return counts\n",
    "def sort_items(counts):\n    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))\n",
    "def top_elements(items):\n    counts = count_items(items)\n    pairs = sort_items(counts)\n    return [k for k, v in pairs]\n",
    'if __name__ == "__main__":\n    print(top_elements(["a", "b", "a"]))\n',
]

AI_PROGRAM = (
    'def count_items(items):\n'
    '    """统计每个元素出现的次数。"""\n'
    "    counts = {}\n"
    "    for it in items:\n"
    "        counts[it] = counts.get(it, 0) + 1\n"
    "    return counts\n"
    "\n"
    "\n"
    'def sort_items(counts):\n'
    '    """按出现次数降序、元素升序排序。"""\n'
    "    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))\n"
    "\n"
    "\n"
    'def top_elements(items):\n'
    '    """返回排序后的元素列表。"""\n'
    "    counts = count_items(items)\n"
    "    pairs = sort_items(counts)\n"
    "    return [k for k, v in pairs]\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    '    print(top_elements(["a", "b", "a"]))\n'
)

CAMEL_PROGRAM = (
    "def countItems(items):\n"
    "    counts = {}\n"
    "    for it in items:\n"
    "        counts[it] = counts.get(it, 0) + 1\n"
    "    return counts\n"
    "\n"
    "\n"
    "def sortItems(counts):\n"
    "    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))\n"
    "\n"
    "\n"
    "def topElements(items):\n"
    "    counts = countItems(items)\n"
    "    pairs = sortItems(counts)\n"
    "    return [k for k, v in pairs]\n"
)

AI_HELPER = (
    "def normalize_items(items):\n"
    '    """把输入规整为列表并去掉空值。"""\n'
    "    if items is None:\n"
    "        return []\n"
    "    return [it for it in items if it is not None]\n"
)


class Recorder:
    """按时间序记录事件，模拟真实编辑器的采集行为。"""

    def __init__(self, session_id: str, student_id: str, problem_id: str = "p001", seed: int = 7):
        self.session_id = session_id
        self.student_id = student_id
        self.problem_id = problem_id
        self.rng = random.Random(seed)
        self.t = 1_700_000_000_000
        self.events: list = []
        self.code = ""
        self._snap_seq = 0

    def _tick(self, base: int = 1500, spread: int = 2500) -> None:
        self.t += base + self.rng.randint(0, spread)

    def _snapshot(self) -> None:
        self._snap_seq += 1
        self._tick(200, 600)
        self.events.append(
            SnapshotEvent(
                ts=self.t,
                session_id=self.session_id,
                snapshot_id=f"{self.session_id}-s{self._snap_seq}",
                ast_hash=short_hash(self.code),
                code=self.code,
            )
        )

    def type_text(self, text: str, n_segments: int = 4) -> None:
        """模拟逐段键入：多个小编辑事件 + 一次快照。"""
        size = max(1, len(text) // n_segments)
        pos = len(self.code)
        for i in range(0, len(text), size):
            seg = text[i : i + size]
            self.code += seg
            self._tick(300, 900)
            self.events.append(
                EditEvent(
                    ts=self.t,
                    session_id=self.session_id,
                    op="insert",
                    range_start=pos,
                    range_end=pos + len(seg),
                    text_len=len(seg),
                    paste_len=0,
                )
            )
            pos += len(seg)
        self._snapshot()

    def paste_text(self, text: str) -> None:
        """模拟大块粘贴：单个 paste 事件 + 一次快照。"""
        pos = len(self.code)
        self.code += ("" if not self.code or self.code.endswith("\n") else "\n") + text
        self._tick(800, 1200)
        self.events.append(
            EditEvent(
                ts=self.t,
                session_id=self.session_id,
                op="paste",
                range_start=pos,
                range_end=pos + len(text),
                text_len=len(text),
                paste_len=len(text),
                clipboard_hash=short_hash(text),
            )
        )
        self._snapshot()

    def replace(self, old: str, new: str) -> None:
        if old not in self.code:
            return
        self.code = self.code.replace(old, new)
        self._tick(400, 1200)
        self.events.append(
            EditEvent(
                ts=self.t,
                session_id=self.session_id,
                op="replace",
                text_len=len(new),
                paste_len=0,
            )
        )
        self._snapshot()

    def run(self, result: str, error_type: str = "", error_loc: str = "") -> None:
        self._tick(1000, 3000)
        self.events.append(
            RunEvent(
                ts=self.t,
                session_id=self.session_id,
                result=result,
                error_type=error_type,
                error_loc=error_loc,
            )
        )

    def build(self) -> Session:
        session = Session(
            session_id=self.session_id,
            student_id=self.student_id,
            problem_id=self.problem_id,
            events=self.events,
        )
        _fill_next_fix_ms(session)
        return session


def _fill_next_fix_ms(session: Session) -> None:
    """回填 next_fix_ms：运行失败到下一次修复性编辑的间隔。"""
    ordered = session.sorted_events()
    for i, ev in enumerate(ordered):
        if isinstance(ev, RunEvent) and ev.result in ("fail", "error"):
            for later in ordered[i + 1 :]:
                if isinstance(later, EditEvent):
                    ev.next_fix_ms = later.ts - ev.ts
                    break


# ---------------- 四种典型过程 ----------------

def scenario_handwrite(session_id: str = "s-handwrite", student_id: str = "stu-001", seed: int = 11) -> Session:
    """剧本 1：现场手写 —— 渐进编辑 + 多次运行失败与修复。"""
    r = Recorder(session_id, student_id, seed=seed)
    r.type_text(CHUNKS[0], n_segments=5)
    r.run("fail", "NameError", "line 6")
    r.replace("sort_items(counts)", "sort_items(counts)")
    r.run("pass")
    r.type_text(CHUNKS[1], n_segments=4)
    r.run("fail", "TypeError", "line 9")
    r.type_text(CHUNKS[2], n_segments=5)
    r.run("pass")
    r.type_text(CHUNKS[3], n_segments=3)
    r.run("pass")
    return r.build()


def scenario_paste_ai(session_id: str = "s-paste-ai", student_id: str = "stu-002", seed: int = 23) -> Session:
    """剧本 2：粘贴 AI 生成结果后微调 —— 大块粘贴 + 无调试循环。"""
    r = Recorder(session_id, student_id, seed=seed)
    r.paste_text(AI_PROGRAM)
    for _ in range(3):
        r.replace("counts.get", "counts.get")
    r.replace("kv", "pair")
    r.replace("pair", "kv")
    r.replace("sorted", "sorted")
    r.run("pass")
    return r.build()


def scenario_copy_classmate(session_id: str = "s-copy", student_id: str = "stu-003", seed: int = 37) -> Session:
    """剧本 3：抄同学代码后批量改名 —— 大块粘贴 + 风格漂移。"""
    r = Recorder(session_id, student_id, seed=seed)
    r.paste_text(CAMEL_PROGRAM)
    r.replace("countItems", "count_items")
    r.replace("sortItems", "sort_items")
    r.replace("topElements", "top_elements")
    r.run("pass")
    return r.build()


def scenario_local_ai_assist(
    session_id: str = "s-local-assist", student_id: str = "stu-004", seed: int = 41
) -> Session:
    """剧本 4：手写为主 + 局部 AI 补全 —— 应有局部高亮，但不判全篇异常。"""
    r = Recorder(session_id, student_id, seed=seed)
    r.type_text(CHUNKS[0], n_segments=5)
    r.run("fail", "NameError", "line 5")
    r.type_text(CHUNKS[1], n_segments=4)
    r.run("pass")
    r.type_text(CHUNKS[2], n_segments=5)
    r.run("fail", "TypeError", "line 12")
    r.replace("count_items(items)", "count_items(items)")
    r.run("pass")
    r.paste_text(AI_HELPER)
    r.run("pass")
    return r.build()


SCENARIOS = {
    "handwrite": ("剧本1 现场手写", scenario_handwrite),
    "paste_ai": ("剧本2 粘贴AI结果", scenario_paste_ai),
    "copy_classmate": ("剧本3 抄同学后改名", scenario_copy_classmate),
    "local_ai_assist": ("剧本4 手写+局部AI补全", scenario_local_ai_assist),
}


def build_all() -> dict[str, Session]:
    return {key: fn() for key, (_, fn) in SCENARIOS.items()}


def scenario_label(key: str) -> str:
    return SCENARIOS[key][0] if key in SCENARIOS else key
