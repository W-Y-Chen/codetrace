from codetrace.astutil import function_subtrees, parse_code
from codetrace.evolution import build_evolution, make_snapshot, mutation_points, median, quantile
from codetrace.events import SnapshotEvent


def snap(sid, ts, code):
    return make_snapshot(SnapshotEvent(ts=ts, session_id="s", snapshot_id=sid, code=code))


def test_function_subtrees_extracted():
    ir = parse_code("def foo():\n    return 1\ndef bar():\n    return 2\n")
    funcs = function_subtrees(ir)
    assert set(funcs) == {"foo", "bar"}


def test_first_edge_from_empty_flagged():
    snaps = [snap("s0", 1, ""), snap("s1", 2, "def foo():\n    return 1\n")]
    edges = build_evolution(snaps)
    assert len(edges) == 1
    assert edges[0].from_empty is True


def test_adding_function_produces_positive_dsem():
    snaps = [
        snap("s0", 1, "def foo():\n    return 1\n"),
        snap("s1", 2, "def foo():\n    return 1\ndef bar():\n    return 2\n"),
    ]
    edges = build_evolution(snaps)
    assert edges[0].dsem > 0
    assert "bar" in edges[0].added


def test_identical_snapshots_zero_dsem():
    code = "def foo():\n    return 1\n"
    edges = build_evolution([snap("s0", 1, code), snap("s1", 2, code)])
    assert edges[0].dsem == 0.0


def test_unparsable_snapshot_does_not_crash():
    snaps = [snap("s0", 1, "def foo(:\n"), snap("s1", 2, "def foo():\n    return 1\n")]
    edges = build_evolution(snaps)
    assert len(edges) == 1
    assert isinstance(edges[0].dsem, float)


def test_mutation_points_detects_spike():
    base = "def foo():\n    return 1\n"
    snaps = [snap("s0", 1, base)]
    for i in range(1, 6):
        snaps.append(snap(f"s{i}", 10 * i, base + f"# c{i}\n"))
    snaps.append(snap("big", 99, base + "def bar():\n    return 2\ndef baz():\n    return 3\n"))
    edges = [e for e in build_evolution(snaps) if not e.from_empty]
    muts = mutation_points(edges, factor=3.0, min_abs=0.3)
    assert len(muts) >= 1
    assert muts[-1].dsem >= max(e.dsem for e in edges[:-1])


def test_median_and_quantile():
    assert median([1, 2, 3]) == 2
    assert median([1, 2, 3, 4]) == 2.5
    assert median([]) == 0.0
    assert quantile([1, 2, 3, 4, 5], 0.75) == 4
