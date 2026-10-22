from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collector import Collector
from pep848_sim.heap import Heap
from pep848_sim.structures import (
    Build,
    Chains,
    Root,
    Shape,
    StructureParameters,
    Tree,
)
from test_heap import reachable


def long_lived(shape: Shape, size: int, root: Root) -> StructureParameters:
    return StructureParameters(
        shape=shape,
        size=size,
        root=root,
        lifetime=None,
        rebuild_interval=None,
        build_churn=0,
    )


def built(heap: Heap, parameters: StructureParameters) -> Build:
    build = Build(heap, parameters)
    while not build.done:
        build.add()
    return build


@pytest.mark.parametrize("root", ["module", "frame"])
def test_a_dropped_tree_with_parent_pointers_becomes_cyclic_garbage(
    root: Root,
) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Tree(), 7, root))

    build.drop()

    assert heap.uncollected_garbage == 7
    assert len(set(collector.nursery) - reachable(heap)) == 7


def test_a_lone_tree_root_lies_on_no_cycle_and_goes_on_the_spot() -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Tree(), 1, "frame"))

    build.drop()

    assert heap.uncollected_garbage == 0
    assert list(collector.nursery) == [heap.module_root]


@pytest.mark.parametrize("root", ["module", "frame"])
def test_refcounting_frees_dropped_chains_on_the_spot(root: Root) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Chains(width=3), 10, root))

    build.drop()

    assert heap.uncollected_garbage == 0
    assert list(collector.nursery) == [heap.module_root]


def test_chains_put_each_new_object_on_the_next_chain_in_turn() -> None:
    collector = Collector()
    heap = Heap(collector)
    build = Build(heap, long_lived(Chains(width=2), 6, "module"))

    for _ in range(6):
        assert not build.done
        build.add()

    assert build.done
    root, a, b, c, d, e = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, a, b, c, d, e)] == [
        (a, b),
        (c,),
        (d,),
        (e,),
        (),
        (),
    ]
    assert heap.references(heap.module_root) == (root,)
    assert heap.frame_roots() == {}
    assert heap.clock == 6


def test_a_tree_links_each_node_and_its_parent_both_ways() -> None:
    collector = Collector()
    heap = Heap(collector)

    built(heap, long_lived(Tree(), 5, "frame"))

    root, a, b, c, d = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, a, b, c, d)] == [
        (a, b),
        (root, c, d),
        (root,),
        (a,),
        (a,),
    ]
    assert heap.references(heap.module_root) == ()
    assert heap.frame_roots() == {root: 1}
    assert heap.clock == 5


def test_a_build_that_outlasts_its_rebuild_interval_is_refused() -> None:
    def repeating(rebuild_interval: int) -> StructureParameters:
        # Ten objects, each followed by two churn allocations: a 30 kB build.
        return StructureParameters(
            shape=Tree(),
            size=10,
            root="frame",
            lifetime=20,
            rebuild_interval=rebuild_interval,
            build_churn=2,
        )

    repeating(30)
    with pytest.raises(ValueError, match="outlasts"):
        repeating(29)


@given(
    st.one_of(st.builds(Chains, width=st.integers(1, 8)), st.just(Tree())),
    st.integers(min_value=1, max_value=40),
    st.sampled_from(["module", "frame"]),
    st.data(),
)
def test_a_structure_keeps_the_counts_true_and_its_drop_counts_its_cycles(
    shape: Shape, size: int, root: Root, data: st.DataObject
) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = Build(heap, long_lived(shape, size, root))

    for _ in range(data.draw(st.integers(min_value=0, max_value=size))):
        build.add()

    built_so_far = list(collector.nursery)[1:]
    frame_roots = {built_so_far[0]: 1} if root == "frame" and built_so_far else {}
    assert heap.frame_roots() == frame_roots
    held = Counter(t for x in collector.nursery for t in heap.references(x))
    held.update(frame_roots)
    held[heap.module_root] += 1  # the interpreter holds sys
    assert all(heap.reference_count(x) == held[x] for x in collector.nursery)

    while not build.done:
        build.add()
    build.drop()

    assert heap.uncollected_garbage == len(set(collector.nursery) - reachable(heap))
