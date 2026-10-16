import pytest

from codetrace.ted import (
    DEFAULT_MAX_NODES,
    TNode,
    layered_distance,
    multiset_distance,
    node_count,
    serialize,
    tree_edit_distance,
)


def n(label, *children):
    return TNode(label, list(children))


def test_identical_tree_distance_zero():
    t = n("A", n("B"), n("C"))
    assert tree_edit_distance(t, t) == 0


def test_single_node_rename_cost_one():
    assert tree_edit_distance(n("A"), n("B")) == 1


def test_insert_leaf_cost_one():
    assert tree_edit_distance(n("A"), n("A", n("B"))) == 1


def test_delete_leaf_cost_one():
    assert tree_edit_distance(n("A", n("B"), n("C")), n("A", n("C"))) == 1


def test_nested_rename_cost_one():
    t1 = n("A", n("B", n("C")))
    t2 = n("A", n("B", n("D")))
    assert tree_edit_distance(t1, t2) == 1


def test_disjoint_subtree_cost():
    t1 = n("A", n("B"), n("C"))
    t2 = n("A", n("X"), n("Y"))
    assert tree_edit_distance(t1, t2) == 2


def test_serialize_is_canonical():
    t = n("A", n("B"), n("C"))
    assert serialize(t) == "A(B,C)"


def test_node_count():
    assert node_count(n("A", n("B"), n("C"))) == 3


def test_multiset_distance_symmetric_difference():
    t1 = n("A", n("B"))
    t2 = n("A", n("C"))
    assert multiset_distance(t1, t2) == 2


def test_layered_distance_degrades_on_large_tree():
    big = TNode("root")
    cur = big
    for i in range(DEFAULT_MAX_NODES + 20):
        child = TNode(f"n{i}")
        cur.children.append(child)
        cur = child
    small = n("root", n("x"))
    dist, degraded = layered_distance(big, small)
    assert degraded is True
    assert dist == float(multiset_distance(big, small))


def test_layered_distance_exact_below_threshold():
    t1 = n("A", n("B"), n("C"))
    t2 = n("A", n("C"))
    dist, degraded = layered_distance(t1, t2)
    assert degraded is False
    assert dist == 1.0
