from typing import override

from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import (
    CollectionCounts,
    CollectorSettings,
    Record,
    find_unreachable,
)
from pep848_sim.collectors.heap import Heap
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.structures import StructureParameters
from pep848_sim.workload import ChurnParameters, Workload, WorkloadParameters
from test_heap import reachable
from test_workload import churn_parameters, structure_parameters


def test_a_young_collection_follows_the_pseudocode_line_by_line() -> None:
    # One aging space, and no collection until the test asks for one.
    settings = CollectorSettings(threshold0=1_000, threshold1=2)
    collector = IncrementalCollector(settings)
    heap = Heap(collector)
    held = heap.allocate()  # its allocating frame holds it
    a, b = heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(a, leaves_unreachable=2)
    first_nursery = collector.nursery
    assert list(collector.reachable) == [heap.module_root]
    assert list(first_nursery) == [held, a, b]

    # The oldest aging space is the empty one the collector started with.
    collector.young_collection()

    assert collector.aging == [first_nursery]
    second_nursery = collector.nursery
    assert list(second_nursery) == []
    assert list(collector.visited_space) == []
    assert collector.work_to_do == -6_250

    collector.young_collection()

    # oldest = aging.pop(); survivors = collect_cycles(oldest)
    assert [heap.is_freed(x) for x in (a, b)] == [True, True]
    assert heap.uncollected_garbage == 0
    # work_to_do += len(survivors); visited_space.extend(survivors)
    assert collector.work_to_do == -6_250 + 1
    assert list(collector.visited_space) == [held]
    # aging.insert(0, nursery); nursery = []
    assert collector.aging == [second_nursery]
    assert collector.nursery is not second_nursery
    assert list(collector.nursery) == []


def test_collections_alternate_from_an_old_one_and_young_ones_start_idle() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=10))
    heap = Heap(collector)
    first = [heap.allocate() for _ in range(8)]
    a, b = heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(a, leaves_unreachable=2)

    # Through clock 120, where the twelfth collection runs.
    for _ in range(111):
        heap.allocate_unseen()

    assert [counts.kind for counts in collector.counts] == ["old", "young"] * 6
    young = [counts for counts in collector.counts if counts.kind == "young"]
    # Five aging spaces, all empty at first; the sixth takes the first nursery.
    assert [(c.survived, c.freed, c.work) for c in young] == [(0, 0, 0)] * 5 + [
        (8, 2, 10)
    ]
    assert list(collector.visited_space) == first


class Recorded(IncrementalCollector):
    """An incremental collector whose budget starts at 0, so that old collections
    run within a short run. It notes the budget around each collection, and at each
    swap the cyclic garbage wholly in the old generation."""

    def __init__(self, settings: CollectorSettings) -> None:
        super().__init__(settings)
        self.work_to_do = 0
        # Each collection's budget before and after, whether it swapped, and its
        # counts.
        self.budgets: list[tuple[int, int, bool, CollectionCounts]] = []
        self.garbage_at_swaps: list[list[int]] = []
        # At each swap, what the last swap found that is still alive.
        self.left_by_sweeps: list[list[int]] = []

    @override
    def attach(self, heap: Heap) -> None:
        super().attach(heap)
        self.heap = heap

    @override
    def collect(self) -> None:
        before, pending = self.work_to_do, self.pending_space
        super().collect()
        swapped = self.pending_space is not pending
        self.budgets.append((before, self.work_to_do, swapped, self.counts[-1]))
        if swapped:
            if self.garbage_at_swaps:
                last = self.garbage_at_swaps[-1]
                self.left_by_sweeps.append(
                    [x for x in last if not self.heap.is_freed(x)]
                )
            self.garbage_at_swaps.append(
                find_unreachable(self.heap, self.pending_space)
            )


@given(
    churn_parameters(),
    st.lists(structure_parameters(), max_size=2),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=1, max_value=6),
    st.lists(st.integers(min_value=0, max_value=600), max_size=4),
)
def test_a_run_keeps_the_incremental_collectors_invariants(
    churn: ChurnParameters,
    structures: list[StructureParameters],
    seed: int,
    threshold0: int,
    threshold1: int,
    stops: list[int],
) -> None:
    """The workloads' garbage never holds other garbage, so each sweep frees the
    cyclic garbage wholly in the old generation when it starts."""
    settings = CollectorSettings(threshold0=threshold0, threshold1=threshold1)
    collector = Recorded(settings)
    heap = Heap(collector)
    workload = Workload(heap, WorkloadParameters(churn, tuple(structures), seed))

    for stop in sorted(stops):
        workload.run_to(stop)

        spaces = [
            collector.nursery,
            *collector.aging,
            collector.pending_space,
            collector.visited_space,
            collector.reachable,
        ]
        placed = [x for space in spaces for x in space]
        assert len(placed) == len(set(placed)) == len(heap)
        assert [x for x in placed if heap.is_freed(x)] == []
        reached = reachable(heap)
        assert [x for x in reached if heap.is_freed(x)] == []
        assert heap.uncollected_garbage == len(set(placed) - reached)

    for before, after, swapped, counts in collector.budgets:
        if counts.kind == "young":
            assert after == before + counts.survived
        elif swapped:
            assert after == 0
        else:
            assert after == before - counts.marked - counts.survived + counts.freed
    assert [left for left in collector.left_by_sweeps if left] == []


def test_a_full_collection_marks_what_sys_reaches_and_examines_the_rest() -> None:
    settings = CollectorSettings(threshold0=1_000, threshold1=2)
    collector = IncrementalCollector(settings)
    heap = Heap(collector)
    sys = heap.module_root
    m = heap.allocate()
    heap.link(sys, m)
    heap.let_go_frame_root(m)
    held = heap.allocate()  # its allocating frame holds it
    a, b, c, d = (heap.allocate() for _ in range(4))
    for x, y in [(a, b), (b, a), (c, d), (d, c)]:
        heap.link(x, y)
    for x in (b, a, d, c):
        heap.let_go_frame_root(x, leaves_unreachable=2 * (x in (a, c)))
    # One cycle across the old spaces, and one across the young generation.
    collector.pending_space.extend([m, a])
    collector.visited_space.extend([held, b])
    collector.aging[0].extend([c])
    collector.work_to_do = 5
    collector.young_next = True

    collector.collect_full("full")

    # sys and m are marked, held survives, and both cycles are freed.
    assert collector.counts == [CollectionCounts("full", 2, 1, 4)]
    assert [heap.is_freed(x) for x in (a, b, c, d)] == [True] * 4
    assert heap.uncollected_garbage == 0
    assert list(collector.visited_space) == [sys, m, held]
    young = [collector.nursery, *collector.aging]
    old = [collector.pending_space, collector.reachable]
    assert [list(space) for space in young + old] == [[]] * 4
    assert collector.work_to_do == 0
    # Collections alternate as before, and the sweep has not ended yet.
    assert collector.young_next
    assert collector.sweeps == 0


def test_after_a_full_collection_the_next_old_collection_starts_a_sweep() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    held = heap.allocate()
    collector.collect_full("full")
    collector.work_to_do = 3

    collector.old_collection()

    assert list(collector.pending_space) == [held]
    assert list(collector.reachable) == [sys]
    assert collector.work_to_do == 0
    assert collector.sweeps == 1


def test_an_old_collection_follows_the_pseudocode_line_by_line() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    m1, m2 = heap.allocate(), heap.allocate()
    heap.link(sys, m1)
    heap.link(m1, m2)
    heap.let_go_frame_root(m1)
    heap.let_go_frame_root(m2)
    held = heap.allocate()  # its allocating frame holds it
    a, b = heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(a, leaves_unreachable=2)
    # The old generation, least recently scanned first.
    collector.pending_space.extend([m1, m2, held, a, b])
    collector.work_to_do = 10

    collector.collect()  # a new collector's first collection is an old one

    # scan_reachable(10) marks sys and the chain it holds: 10 - 3.
    # The increment [held] survives: 7 - 1.
    # The increment [a, b] is cyclic garbage: 6 - 2 + 2 * 2.
    # pending_space runs empty: the spaces swap, sys goes back on reachable, and
    # work_to_do = 0 ends the sweep.
    assert [heap.is_freed(x) for x in (a, b)] == [True, True]
    assert list(collector.pending_space) == [m1, m2, held]
    assert list(collector.visited_space) == []
    assert list(collector.reachable) == [sys]
    assert collector.work_to_do == 0
    assert collector.counts == [CollectionCounts("old", 3, 1, 2)]


def test_marking_takes_from_pending_alone_and_stops_where_the_budget_does() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    m1, m2, young = heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(sys, m1)
    heap.link(sys, young)
    heap.link(m1, m2)
    for x in (m1, m2, young):
        heap.let_go_frame_root(x)
    collector.pending_space.extend([m1, m2])
    collector.work_to_do = 2

    collector.old_collection()

    # scan_reachable(2) moves sys and m1, leaves m2 on reachable, and leaves the
    # young object where it is.
    assert list(collector.visited_space) == [sys, m1]
    assert list(collector.reachable) == [m2]
    assert list(collector.nursery) == [young]

    collector.work_to_do = 1
    collector.old_collection()

    assert list(collector.visited_space) == [sys, m1, m2]
    assert list(collector.reachable) == []


def test_the_next_old_collection_resumes_where_the_budget_ran_out() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    p, q, r = heap.allocate(), heap.allocate(), heap.allocate()  # frames hold them
    collector.pending_space.extend([p, q, r])
    collector.work_to_do = 2

    collector.collect()

    # Marking takes sys, and an increment takes the least recently scanned
    # pending object.
    assert list(collector.visited_space) == [sys, p]
    assert list(collector.pending_space) == [q, r]
    assert collector.work_to_do == 0

    collector.collect()  # a young collection, with nothing to collect
    collector.work_to_do = 1
    collector.collect()

    assert list(collector.visited_space) == [sys, p, q]
    assert list(collector.pending_space) == [r]
    assert collector.counts == [
        CollectionCounts("old", 1, 1, 0),
        CollectionCounts("young", 0, 0, 0),
        CollectionCounts("old", 0, 1, 0),
    ]


def test_an_old_collection_without_a_positive_budget_is_idle() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    x = heap.allocate()
    collector.pending_space.append(x)
    collector.work_to_do = 0

    collector.collect()

    assert list(collector.reachable) == [heap.module_root]
    assert list(collector.pending_space) == [x]
    assert collector.counts == [CollectionCounts("old", 0, 0, 0)]


def test_an_older_cycle_that_a_newer_one_holds_waits_for_the_next_sweep() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    a1, a2, b1, b2 = (heap.allocate() for _ in range(4))
    heap.link(a1, a2)
    heap.link(a2, a1)
    heap.link(b1, b2)
    heap.link(b2, b1)
    heap.link(b1, a1)
    for x in (a1, a2, b2):
        heap.let_go_frame_root(x)
    heap.let_go_frame_root(b1, leaves_unreachable=4)
    collector.pending_space.extend([a1, a2, b1, b2])
    collector.work_to_do = 100

    collector.old_collection()

    # The increment from a1 holds a1 and a2 alone, and b1 holds a1 from outside it.
    assert [heap.is_freed(x) for x in (a1, a2, b1, b2)] == [False, False, True, True]
    assert list(collector.pending_space) == [a1, a2]
    assert heap.uncollected_garbage == 2

    collector.work_to_do = 100
    collector.old_collection()

    assert [heap.is_freed(x) for x in (a1, a2)] == [True, True]
    assert heap.uncollected_garbage == 0


def test_each_collection_leaves_a_record_of_the_heap_before_and_after_it() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=5, threshold1=2))
    heap = Heap(collector)
    heap.allocate()  # its allocating frame holds it
    a, b = heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(a, leaves_unreachable=2)

    # Through clock 20, where the fourth collection runs.
    for _ in range(18):
        heap.allocate_unseen()

    # Spaces: nursery, aging, pending, visited (sys on reachable among them).
    idle = (0, 0, 0, -6_250, 0)
    assert collector.records == [
        Record(5, "old", *idle, (3, 0, 0, 1), (3, 0, 0, 1), 2, 2),
        Record(10, "young", *idle, (3, 0, 0, 1), (0, 3, 0, 1), 2, 2),
        Record(15, "old", *idle, (0, 3, 0, 1), (0, 3, 0, 1), 2, 2),
        Record(20, "young", 0, 1, 2, -6_249, 0, (0, 3, 0, 1), (0, 0, 0, 2), 2, 2),
    ]


def test_an_old_collections_record_carries_the_budget_and_the_sweep() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=5))
    heap = Heap(collector)
    collector.work_to_do = 10

    for _ in range(6):
        heap.allocate_unseen()

    # Marking takes sys (10 - 1); pending_space is empty, so the spaces swap, the
    # budget goes to 0 and the first sweep ends.
    assert collector.records == [
        Record(5, "old", 1, 0, 0, 0, 1, (0, 0, 0, 1), (0, 0, 0, 1), 1, 1)
    ]
