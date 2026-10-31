import json
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import (
    Amazon0302,
    Chains,
    Graph,
    Hierarchy,
    Own,
    Rings,
    Shape,
    TaskGroups,
    Tree,
)
from pep848_sim.widget.graph import graph, sample
from pep848_sim.widget.request import Request, dump
from pep848_sim.workload import WorkloadParameters
from test_structures import DOUBLY_LINKED, long_lived
from test_workload import QUIET


def test_chains_sample_four_chains_three_objects_deep_on_no_cycle() -> None:
    drawn = sample(long_lived(Chains(width=16), 350, "module"))

    # The module, then the first four chains, each 16 objects on from the last.
    assert [i for i, _ in drawn.objects] == [
        0,
        *range(1, 5),
        *range(17, 21),
        *range(33, 37),
    ]
    assert not any(cycle for *_, cycle in drawn.links)


def test_a_tree_samples_four_levels_with_every_link_on_a_cycle() -> None:
    drawn = sample(long_lived(Tree(), 350, "module"))

    assert Counter(level for _, level in drawn.objects) == {0: 1, 1: 2, 2: 4, 3: 8}
    # Each object and its parent link each other.
    assert len(drawn.links) == 2 * 14
    assert all(cycle for *_, cycle in drawn.links)


def test_a_hierarchy_samples_six_children_of_six_children_on_no_cycle() -> None:
    drawn = sample(long_lived(Hierarchy(branches=50), 322, "frame"))

    assert Counter(level for _, level in drawn.objects) == {0: 1, 1: 6, 2: 36}
    assert not any(cycle for *_, cycle in drawn.links)


def test_rings_of_one_object_each_link_to_themselves_on_a_cycle() -> None:
    drawn = sample(long_lived(Rings(length=1), 132, "frame"))

    assert [i for i, _ in drawn.objects] == list(range(11))
    on_cycles = {(s, t) for s, t, cycle in drawn.links if cycle}
    assert on_cycles == {(i, i) for i in range(1, 11)}


def test_a_graph_samples_its_roots_cycle_and_edges_two_nodes_share() -> None:
    drawn = sample(long_lived(Graph(edges=2), 89_007, "module"))

    # The globals and the function that reads them.
    assert {(s, t) for s, t, cycle in drawn.links if cycle} == {(0, 1), (1, 0)}
    holders = Counter(t for _, t, _ in drawn.links)
    assert holders.most_common(1)[0][1] == 2


def test_a_sample_of_an_own_shape_keeps_its_first_forty_objects() -> None:
    drawn = sample(long_lived(Own(DOUBLY_LINKED), 1000, "frame"))

    # A list as deep as the sample's objects last, each one linked both ways.
    assert drawn.objects == [(i, i) for i in range(40)]
    assert all(cycle for *_, cycle in drawn.links)


@given(
    st.one_of(
        st.builds(Chains, width=st.integers(1, 8)),
        st.just(Tree()),
        st.builds(Hierarchy, branches=st.integers(1, 8)),
        st.builds(Graph, edges=st.integers(0, 4)),
        st.just(Amazon0302()),
        st.just(TaskGroups()),
        st.builds(Rings, length=st.integers(1, 8)),
    ),
    st.integers(min_value=1, max_value=200),
)
def test_a_sample_hangs_from_its_first_object_and_shows_cycles_as_a_drop_leaves_them(
    shape: Shape, size: int
) -> None:
    drawn = sample(long_lived(shape, size, "frame"))

    level = dict(drawn.objects)
    assert level[0] == 0
    assert all(s in level and t in level for s, t, _ in drawn.links)
    # Every object past the first hangs from one a level up.
    above = {t for s, t, _ in drawn.links if level[s] + 1 == level[t]}
    assert above == set(level) - {0}
    # The sample has a cycle when a drop leaves cyclic garbage.
    has_cycle = any(cycle for *_, cycle in drawn.links)
    assert has_cycle == (shape.cyclic_garbage(size) > 0)


def test_a_requests_graph_holds_each_structure_and_the_churn() -> None:
    request = json.dumps(
        {
            "preset": "xml_etree_parse",
            "settings": {"threshold0": 2000, "threshold1": 10, "threshold2": 10},
            "every": 5,
        }
    )

    drawn = json.loads(graph(request))

    fields = (
        "shape",
        "size",
        "root",
        "lifetime",
        "rebuild_interval",
        "built_in_c",
        "delay",
        "skips_while_busy",
    )
    assert [tuple(s[field] for field in fields) for s in drawn["structures"]] == [
        ("a tree with parent pointers", 8, "frame", 0, None, False, 0, False),
        ("16 chains", 121, "module", None, None, False, 0, False),
        ("a tree with parent pointers", 401, "module", None, None, False, 0, False),
        ("a tree with parent pointers", 5, "frame", 0, None, False, 0, False),
        ("a tree with parent pointers", 389, "module", None, None, False, 0, False),
        ("16 chains", 232, "frame", None, None, False, 0, False),
        ("a hierarchy of 50 branches", 322, "frame", 25_848, 25_848, False, 0, False),
        ("16 chains", 4, "frame", 0, 25_848, False, 0, False),
        ("a hierarchy of 50 branches", 322, "frame", 719, 359, True, 2_410, True),
        ("16 chains", 4, "frame", 0, 25_848, False, 23_913, False),
        ("a tree with parent pointers", 2, "frame", 0, None, False, 0, False),
        ("16 chains", 82, "frame", 0, None, False, 0, False),
    ]
    assert all(s["objects"] and s["links"] for s in drawn["structures"])
    assert drawn["churn"] == {
        "cycle_share": "0",
        "cycle_size": 1,
        "lifetime_mean": 1,
        "long_share": "0",
        "long_lifetimes": [1, 1],
    }


@pytest.mark.parametrize(
    ("shape", "label"),
    [
        (Chains(width=16), "16 chains"),
        (Tree(), "a tree with parent pointers"),
        (Hierarchy(branches=6), "a hierarchy of 6 branches"),
        (Graph(edges=2), "a graph of 2 edges a node"),
        (Amazon0302(), "networkx's amazon0302 graph"),
        (TaskGroups(), "asyncio's tasks in TaskGroups"),
        (Rings(length=1), "rings of 1 object"),
        (Rings(length=21), "rings of 21 objects"),
        (Own(DOUBLY_LINKED), "a shape of your own"),
    ],
)
def test_the_legend_names_each_shape(shape: Shape, label: str) -> None:
    workload = WorkloadParameters(QUIET, (long_lived(shape, 10, "frame"),), 848)
    request = dump(Request(workload, CollectorSettings(), 100, 1))

    [structure] = json.loads(graph(request))["structures"]

    assert structure["shape"] == label
