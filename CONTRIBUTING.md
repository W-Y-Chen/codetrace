# 贡献指南

CodeTrace 码迹是面向高校编程教学的**过程性原创性判定**原型。评价对象是"代码的产生过程"，不是最终文本；系统只输出可点击的过程证据与三档分级结论，**不输出二元"作弊/未作弊"判定**。

提交前请先读这一页——有两条不可逾越的设计红线。

---

## 一、本地跑起来（零第三方依赖）

```bash
# v0.1 只用 Python 标准库，无需 pip install，Python 3.9+ 即可
python scripts/run_demo.py                 # 跑通四个演示剧本
python -m pytest -q                        # 46 项测试
python scripts/gen_samples.py              # 生成样例事件文件
python -m codetrace.server --port 8765     # 演示服务 http://127.0.0.1:8765
```

Windows 上若用隔离环境，请使用该环境的 `python.exe` 全路径调用。

---

## 二、两条设计红线（PR 若违反将直接关闭）

### 红线一：不产出二元判定

```python
# decision.py
FORBIDDEN_FIELDS = {"is_cheating", "cheating", "ai_generated", "plagiarism", ...}
```

任何返回路径都不得包含二元原创性判定字段，由 `Verdict.validate()` 与 `tests/test_decision.py` 双重保证。**不要为了"好用"而加一个 `is_cheating` 布尔字段。**

### 红线二：不采集代码全文

编辑事件只记录操作类型、变更范围、变更长度与剪贴板来源长度/摘要，**不记录代码文本内容**。这是隐私最小化设计的硬性要求。新增事件字段前请先确认它不承载代码文本。

---

## 三、其它约定

- **零第三方依赖优先**。核心算法层（`codetrace/`）保持纯标准库；若确需引入依赖，请放进可选模块并在 README 的"已知局限"里说明。
- **模拟数据必须标注**。`simulate.py` 生成的是模拟事件，README 与文档中凡引用其结果处必须写明"模拟数据，非真实指标"。
- **未实测的数字不得写进文档**。`baseline.py` 的 `GLOBAL_BASELINE` 目前是设计假设值，未经真实数据标定前不得用于正式评估。
- 提交规范：Conventional Commits（`feat:` / `fix:` / `docs:` / `test:` / `refactor:`）。
- 新增通道或改变融合规则时，必须同步更新 `tests/` 与 README 的"已知局限"。

---

## 四、提 Issue

- **Bug**：附复现命令与完整输出（`python scripts/run_demo.py` 的结果）；
- **算法讨论**：请说明它是否影响 FPR 优先这一设计取舍（本项目把误判率置于检出率之上）；
- **真实数据**：若你所在学校愿意参与"30 人 × 6 题 × 3 方式"的对照数据采集，非常欢迎——这是当前最大的落地缺口。

---

## 五、不要做的事

- 不要在 README/文档中把模拟结果写成真实检出率；
- 不要把尚在原型阶段的能力画像模块写成已完成；
- 不要为了演示效果而删除"诚实清单"章节。
