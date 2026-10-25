from dataclasses import dataclass, field
from itertools import pairwise
from typing import Literal, override

from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import (
    Collector,
    CollectorSettings,
    FullKind,
    Record,
    Space,
    find_unreachable,
)
from pep848_sim.collectors.heap import Heap
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.structures import StructureParameters
from pep848_sim.workload import ChurnParameters, Workload, WorkloadParameters
from test_heap import Built, built_heaps, reachable, reached_from
from test_workload import churn_parameters, structure_parameters

ENDS: tuple[Literal[0, -1], ...] = (0, -1)


@dataclass
class Spaced:
    collector: Collector = field(default_factory=Collector)
    # The nursery first, then every other space, in the order the test made them.
    spaces: list[Space] = field(default_factory=list)
    # The test's own record of each space, in the order its objects entered.
    contents: list[list[int]] = field(default_factory=list)


@st.composite
def spaced_collectors(draw: st.DrawFn) -> Spaced:
    """A heap's collector after random allocations, appends, pops, removals and new
    nurseries."""
    spaced = Spaced()
    collector = spaced.collector
    heap = Heap(collector)
    spaced.spaces = [collector.nursery, Space(collector), Space(collector)]
    spaced.contents = [[heap.module_root], [], []]
    objects = [heap.module_root]
    for _ in range(draw(st.integers(min_value=0, max_value=60))):
        action = draw(
            st.sampled_from(["allocate", "append", "pop", "remove", "new nursery"])
        )
        held = [i for i, content in enumerate(spaced.contents) if content]
        if action == "allocate":
            x = heap.allocate()
            objects.append(x)
            spaced.contents[0].append(x)
        elif action == "append":
            x = draw(st.sampled_from(objects))
            to = draw(st.integers(min_value=0, max_value=len(spaced.spaces) - 1))
            spaced.spaces[to].append(x)
            for content in spaced.contents:
                if x in content:
                    content.remove(x)
            spaced.contents[to].append(x)
        elif action == "pop" and held:
            i = draw(st.sampled_from(held))
            end = draw(st.sampled_from(ENDS))
            assert spaced.spaces[i].pop(end) == spaced.contents[i].pop(end)
        elif action == "remove" and held:
            i = draw(st.sampled_from(held))
            x = draw(st.sampled_from(spaced.contents[i]))
            spaced.spaces[i].remove(x)
            spaced.contents[i].remove(x)
        elif action == "new nursery":
            collector.nursery = Space(collector)
            spaced.spaces.insert(0, collector.nursery)
            spaced.contents.insert(0, [])
    return spaced


def test_new_objects_enter_the_collectors_nursery_after_those_already_there() -> None:
    collector = Collector()
    heap = Heap(collector)

    a, b = heap.allocate(), heap.allocate()

    assert list(collector.nursery) == [heap.module_root, a, b]


def test_appending_takes_an_object_out_of_its_space_and_puts_it_last() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b = heap.allocate(), heap.allocate()
    visited = Space(collector)

    visited.append(b)
    visited.append(a)

    assert list(collector.nursery) == [heap.module_root]
    assert list(visited) == [b, a]


def test_a_space_pops_from_either_end_and_removes_as_a_list_does() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b, c = heap.allocate(), heap.allocate(), heap.allocate()
    visited = Space(collector)

    visited.extend([c, a, b])

    assert (visited.pop(0), visited.pop()) == (c, b)
    assert (a in visited, c in visited, len(visited)) == (True, False, 1)
    visited.remove(a)
    assert not visited
    assert list(collector.nursery) == [heap.module_root]


def test_extending_a_space_with_another_moves_all_of_it() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b = heap.allocate(), heap.allocate()
    old = Space(collector)

    old.extend(collector.nursery)

    assert list(old) == [heap.module_root, a, b]
    assert list(collector.nursery) == []


def test_new_objects_enter_the_nursery_the_collector_holds_now() -> None:
    collector = Collector()
    heap = Heap(collector)
    a = heap.allocate()
    aging = collector.nursery

    collector.nursery = Space(collector)
    b = heap.allocate()

    assert list(aging) == [heap.module_root, a]
    assert list(collector.nursery) == [b]


@given(spaced_collectors())
def test_each_object_sits_in_one_space_in_the_order_it_entered(
    spaced: Spaced,
) -> None:
    assert [list(space) for space in spaced.spaces] == spaced.contents


def test_it_finds_cyclic_garbage_and_what_that_garbage_alone_holds() -> None:
    heap = Heap(Collector())
    rooted, w = heap.allocate(), heap.allocate()  # rooted keeps its frame root
    holder, x, y = heap.allocate(), heap.allocate(), heap.allocate()
    a, b, c = heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(rooted, w)
    heap.link(holder, x)
    heap.link(x, y)
    heap.link(y, x)
    heap.link(a, b)
    heap.link(b, a)
    heap.link(b, c)
    for held in (w, x, y, b, c):
        heap.let_go_frame_root(held)
    heap.let_go_frame_root(a, leaves_unreachable=3)

    assert find_unreachable(heap, [rooted, w, x, y, a, b, c]) == [a, b, c]


def test_cyclic_garbage_held_from_outside_the_examined_objects_survives() -> None:
    heap = Heap(Collector())
    p, q, c, d = heap.allocate(), heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(p, q)
    heap.link(q, p)
    heap.link(c, d)
    heap.link(d, c)
    heap.link(q, c)
    for x in (q, c, d):
        heap.let_go_frame_root(x)
    heap.let_go_frame_root(p, leaves_unreachable=4)

    assert find_unreachable(heap, [c, d]) == []
    assert find_unreachable(heap, [p, q, c, d]) == [p, q, c, d]


@given(built_heaps(), st.data())
def test_it_finds_what_nothing_outside_the_examined_objects_reaches(
    built: Built, data: st.DataObject
) -> None:
    heap = built.heap
    alive = [x for x in built.objects if not heap.is_freed(x)]
    examined = data.draw(st.lists(st.sampled_from(alive), unique=True))
    outside = [x for x in alive if x not in examined]
    reached = reached_from(heap, [heap.module_root, *built.frame_roots, *outside])

    assert find_unreachable(heap, examined) == [x for x in examined if x not in reached]


def test_collecting_cycles_frees_the_garbage_and_returns_the_survivors() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b, c, d, e = (heap.allocate() for _ in range(5))
    heap.link(a, b)
    heap.link(b, a)
    heap.link(c, d)
    heap.link(d, c)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(d)
    heap.let_go_frame_root(c, leaves_unreachable=2)

    survivors = collector.collect_cycles([a, c, e, b, d])

    assert survivors == [a, e, b]
    assert [heap.is_freed(x) for x in (c, d)] == [True, True]
    assert heap.uncollected_garbage == 0


def test_collecting_a_group_frees_what_the_group_alone_held() -> None:
    collector = Collector()
    heap = Heap(collector)
    outside = heap.allocate()  # its allocating frame holds it
    a, b, c = heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.link(b, c)
    heap.link(a, outside)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(c)
    heap.let_go_frame_root(a, leaves_unreachable=3)

    assert collector.collect_cycles([a, b]) == []

    assert [heap.is_freed(x) for x in (a, b, c)] == [True, True, True]
    assert heap.reference_count(outside) == 1
    assert list(collector.nursery) == [heap.module_root, outside]
    assert heap.uncollected_garbage == 0


def test_collecting_a_group_leaves_a_cycle_it_held_alive_and_counted() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b, c, d = heap.allocate(), heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.link(c, d)
    heap.link(d, c)
    heap.link(b, c)
    for x in (b, c, d):
        heap.let_go_frame_root(x)
    heap.let_go_frame_root(a, leaves_unreachable=4)

    assert collector.collect_cycles([a, b]) == []

    assert [heap.is_freed(x) for x in (a, b, c, d)] == [True, True, False, False]
    assert heap.reference_count(c) == 1
    assert list(collector.nursery) == [heap.module_root, c, d]
    assert heap.uncollected_garbage == 2


def test_collecting_a_group_frees_what_it_kept_for_an_object_the_group_held() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b, outside, s = (heap.allocate() for _ in range(4))
    heap.link(a, b)
    heap.link(b, a)
    heap.link(b, outside)
    heap.link(outside, s)
    for x in (b, outside, s):
        heap.let_go_frame_root(x)
    heap.let_go_frame_root(a, leaves_unreachable=4)

    assert collector.collect_cycles([a, b, s]) == []

    assert [heap.is_freed(x) for x in (a, b, outside, s)] == [True] * 4
    assert (collector.survived, collector.freed) == (0, 3)
    assert list(collector.nursery) == [heap.module_root]
    assert heap.uncollected_garbage == 0


# Around each collection: the alive objects and what the tests' walk reaches,
# before it and after it.
type Walks = list[tuple[int, int, int, int]]


class WalkingIncremental(IncrementalCollector):
    def __init__(self, settings: CollectorSettings) -> None:
        super().__init__(settings)
        self.work_to_do = 0  # so that old collections run within a short run
        self.walks: Walks = []

    @override
    def attach(self, heap: Heap) -> None:
        super().attach(heap)
        self.heap = heap

    @override
    def collect(self) -> None:
        before = len(self.heap), len(reachable(self.heap))
        super().collect()
        self.walks.append((*before, len(self.heap), len(reachable(self.heap))))

    @override
    def collect_full(self, kind: FullKind) -> None:
        before = len(self.heap), len(reachable(self.heap))
        super().collect_full(kind)
        self.walks.append((*before, len(self.heap), len(reachable(self.heap))))


class WalkingLegacy(LegacyCollector):
    def __init__(self, settings: CollectorSettings) -> None:
        super().__init__(settings)
        self.walks: Walks = []

    @override
    def attach(self, heap: Heap) -> None:
        super().attach(heap)
        self.heap = heap

    @override
    def collect(self) -> None:
        before = len(self.heap), len(reachable(self.heap))
        super().collect()
        self.walks.append((*before, len(self.heap), len(reachable(self.heap))))

    @override
    def collect_full(self, kind: FullKind) -> None:
        before = len(self.heap), len(reachable(self.heap))
        super().collect_full(kind)
        self.walks.append((*before, len(self.heap), len(reachable(self.heap))))


def uncollected(spaces: tuple[int, ...], reachable_part: int) -> int:
    return sum(spaces) - reachable_part


@given(
    st.sampled_from([WalkingIncremental, WalkingLegacy]),
    churn_parameters(),
    st.lists(structure_parameters(), max_size=2),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=1, max_value=10),
    st.integers(min_value=0, max_value=3),
    st.integers(min_value=0, max_value=400),
)
def test_each_record_holds_the_heap_and_its_reachable_part_before_and_after(
    walking: type[WalkingIncremental | WalkingLegacy],
    churn: ChurnParameters,
    structures: list[StructureParameters],
    seed: int,
    threshold0: int,
    threshold1: int,
    threshold2: int,
    run_kb: int,
) -> None:
    collector = walking(CollectorSettings(threshold0, threshold1, threshold2))
    heap = Heap(collector)

    Workload(heap, WorkloadParameters(churn, tuple(structures), seed)).run_to(run_kb)

    records: list[Record] = collector.records
    for record, walk in zip(records, collector.walks, strict=True):
        assert (
            sum(record.spaces_before),
            record.reachable_before,
            sum(record.spaces_after),
            record.reachable_after,
        ) == walk
    # Between collections, the workload only adds to the uncollected garbage.
    for previous, record in pairwise(records):
        assert uncollected(record.spaces_before, record.reachable_before) >= (
            uncollected(previous.spaces_after, previous.reachable_after)
        )
