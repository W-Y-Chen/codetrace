import json

import pytest

from codetrace import chain
from codetrace.events import EditEvent, Session, SnapshotEvent
from codetrace.pipeline import analyze, reverify


def _session(n: int = 5) -> Session:
    events = []
    for i in range(n):
        events.append(
            EditEvent(ts=1000 + i, session_id="s1", op="insert", text_len=10, paste_len=0)
        )
    return Session(session_id="s1", student_id="stu", problem_id="p001", events=events)


def test_chain_is_deterministic():
    s = _session()
    a = chain.compute_chain(s.sorted_events(), chain.chain_seed("s1"))
    b = chain.compute_chain(s.sorted_events(), chain.chain_seed("s1"))
    assert a == b
    assert len(a) == 5


def test_chain_changes_when_event_changes():
    s = _session()
    seed = chain.chain_seed("s1")
    before = chain.compute_chain(s.sorted_events(), seed)
    s.events[2].paste_len = 500
    after = chain.compute_chain(s.sorted_events(), seed)
    assert before != after
    assert before[0] == after[0]
    assert before[1] == after[1]
    assert before[2] != after[2]


def test_verify_detects_tampering_and_locates_index():
    s = _session()
    seed = chain.chain_seed("s1")
    hashes = chain.compute_chain(s.sorted_events(), seed)
    ok, bad = chain.verify_chain(s.sorted_events(), hashes, seed)
    assert ok and bad is None

    s.events[3].text_len = 999
    ok, bad = chain.verify_chain(s.sorted_events(), hashes, seed)
    assert ok is False
    assert bad == 3


def test_verify_detects_deletion():
    s = _session()
    seed = chain.chain_seed("s1")
    hashes = chain.compute_chain(s.sorted_events(), seed)
    s.events.pop(2)
    ok, bad = chain.verify_chain(s.sorted_events(), hashes, seed)
    assert ok is False


def test_merkle_root_changes_with_leaves():
    r1 = chain.merkle_root(["a", "b", "c"])
    r2 = chain.merkle_root(["a", "b", "d"])
    assert r1 != r2
    assert chain.merkle_root(["a", "b", "c"]) == r1


def test_package_roundtrip_and_offline_verification():
    s = _session()
    result = analyze(s, problem=None)
    pkg_json = result["package"]
    report = reverify(pkg_json)
    assert report["ok"] is True
    assert report["chain_ok"] is True
    assert report["batches_ok"] is True


def test_package_detects_tampering_offline():
    s = _session()
    result = analyze(s, problem=None)
    pkg = chain.EvidencePackage.from_json(result["package"])
    pkg.events[2]["paste_len"] = 8888
    tampered = pkg.to_json()
    report = reverify(tampered)
    assert report["ok"] is False
    assert report["first_bad_index"] == 2


def test_batches_cover_all_events():
    s = _session(70)
    result = analyze(s, problem=None)
    pkg = chain.EvidencePackage.from_json(result["package"])
    covered = sum(b.end - b.start for b in pkg.batches)
    assert covered == len(pkg.events)
