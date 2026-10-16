import json

import pytest

from codetrace.pipeline import analyze, analyze_events, reverify
from codetrace.simulate import PROBLEM, SCENARIOS


@pytest.mark.parametrize("key", list(SCENARIOS.keys()))
def test_every_scenario_produces_verifiable_package(key):
    session = SCENARIOS[key][1]()
    result = analyze(session, problem=PROBLEM)
    assert result["verdict"]["level_code"] in ("none", "watch", "review")
    assert "disclaimer" in result["verdict"]
    report = reverify(result["package"])
    assert report["ok"] is True


@pytest.mark.parametrize("key", list(SCENARIOS.keys()))
def test_analysis_is_deterministic(key):
    a = analyze(SCENARIOS[key][1](), problem=PROBLEM)
    b = analyze(SCENARIOS[key][1](), problem=PROBLEM)
    assert a["features"] == b["features"]
    assert a["verdict"]["level"] == b["verdict"]["level"]
    assert a["chain_head"] == b["chain_head"]


def test_analyze_events_accepts_raw_dicts():
    session = SCENARIOS["handwrite"][1]()
    from codetrace.events import to_dict

    raw = [to_dict(e) for e in session.sorted_events()]
    result = analyze_events(raw, session_id="raw-1", student_id="stu-raw", problem=PROBLEM)
    assert result["session_id"] == "raw-1"
    assert result["verdict"]["level_code"] == "none"


def test_package_is_self_contained_json():
    session = SCENARIOS["paste_ai"][1]()
    result = analyze(session, problem=PROBLEM)
    pkg = json.loads(result["package"])
    assert pkg["version"] == "codetrace-package-v1"
    assert pkg["events"] and pkg["hashes"]
    assert len(pkg["events"]) == len(pkg["hashes"])
    assert pkg["analysis"]["verdict"]["level_code"] == "review"


def test_diagnostics_report_unparsed_snapshots():
    from codetrace.events import Session, SnapshotEvent

    session = Session(
        session_id="bad",
        student_id="stu",
        problem_id="p001",
        events=[
            SnapshotEvent(ts=1, session_id="bad", snapshot_id="s0", code="def foo(:\n"),
            SnapshotEvent(ts=2, session_id="bad", snapshot_id="s1", code="def foo():\n    return 1\n"),
        ],
    )
    result = analyze(session, problem=PROBLEM)
    assert result["diagnostics"]["unparsed_snapshots"] == 1
