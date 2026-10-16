import pytest

from codetrace.channels import ChannelScore, Evidence
from codetrace.decision import (
    FORBIDDEN_FIELDS,
    LEVEL_NONE,
    LEVEL_REVIEW,
    LEVEL_WATCH,
    Verdict,
    decide,
)
from codetrace.simulate import (
    scenario_copy_classmate,
    scenario_handwrite,
    scenario_local_ai_assist,
    scenario_paste_ai,
)
from codetrace.pipeline import analyze
from codetrace.simulate import PROBLEM


def cs(name, score, n_ev=1, enabled=True):
    evs = [Evidence(channel=name, kind="k", ts=0, detail="d", score=score) for _ in range(n_ev)]
    return ChannelScore(name, score, enabled, evs)


def test_all_three_levels_reachable():
    assert decide({"P1": cs("P1", 0.0), "P2": cs("P2", 0.0)}).level_code == "none"
    assert decide({"P1": cs("P1", 0.4), "P2": cs("P2", 0.0)}).level_code == "watch"
    assert decide({"P1": cs("P1", 0.9), "P2": cs("P2", 0.0)}).level_code == "review"


def test_two_weak_channels_trigger_review():
    v = decide({"P3": cs("P3", 0.7), "P4": cs("P4", 0.7)})
    assert v.level_code == "review"
    assert set(v.strong_channels) == {"P3", "P4"}


def test_verdict_never_exposes_binary_judgement():
    v = decide({"P1": cs("P1", 0.9)})
    v.validate()
    dumped = v.to_dict()
    for field in FORBIDDEN_FIELDS:
        assert field not in dumped
    assert "is_cheating" not in dumped


def test_verdict_rejects_unknown_level():
    v = Verdict(level="作弊", level_code="x", reason="")
    with pytest.raises(ValueError):
        v.validate()


def test_disabled_channel_ignored():
    v = decide({"P5": ChannelScore("P5", 1.0, False, [])})
    assert v.level_code == "none"


def test_handwrite_not_flagged_for_review():
    """误判控制：手写场景不得进入需复核档（方案 §8 M1 的原型级验证）。"""
    result = analyze(scenario_handwrite(), problem=PROBLEM)
    assert result["verdict"]["level_code"] in ("none", "watch"), result["channels"]


def test_paste_ai_flagged_for_review():
    result = analyze(scenario_paste_ai(), problem=PROBLEM)
    assert result["verdict"]["level_code"] == "review"


def test_local_ai_assist_is_localized_not_global():
    """局部 AI 补全：应显著弱于整篇粘贴，且高亮片段更少。"""
    local = analyze(scenario_local_ai_assist(), problem=PROBLEM)
    full = analyze(scenario_paste_ai(), problem=PROBLEM)
    assert local["verdict"]["level_code"] != "review" or len(local["verdict"]["highlights"]) < len(
        full["verdict"]["highlights"]
    )
    assert local["features"]["debug_density"] > full["features"]["debug_density"]


def test_copy_classmate_triggers_style_and_paste():
    result = analyze(scenario_copy_classmate(), problem=PROBLEM)
    ch = result["channels"]
    assert ch["P1"]["score"] >= 0.5
    assert ch["P4"]["score"] >= 0.5
    assert result["verdict"]["level_code"] == "review"
