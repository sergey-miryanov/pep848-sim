from typing import override

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import (
    CollectionCounts,
    CollectorSettings,
    Constants,
    Record,
    find_unreachable,
)
from pep848_sim.collectors.heap import Heap
from pep848_sim.collectors.incremental import IncrementalCollector, OldSpace
from pep848_sim.structures import StructureParameters
from pep848_sim.workload import ChurnParameters, Workload, WorkloadParameters
from test_heap import reachable
from test_run import constants
from test_workload import churn_parameters, structure_parameters


def test_a_young_collection_follows_the_branch_line_by_line() -> None:
    # One aging space, and no collection until the test asks for one.
    settings = CollectorSettings(threshold0=1_000, threshold1=2)
    collector = IncrementalCollector(settings)
    heap = Heap(collector)
    sys = heap.module_root
    held = heap.allocate()  # its allocating frame holds it
    a, b = heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(a, leaves_unreachable=2)
    first_nursery = collector.nursery
    # The branch tracks sys as it tracks any object.
    assert list(collector.reachable) == []
    assert list(first_nursery) == [sys, held, a, b]

    # The oldest aging space is the empty one the collector started with.
    collector.young_collection()

    assert collector.aging == [first_nursery]
    second_nursery = collector.nursery
    assert list(second_nursery) == []
    assert list(collector.visited_space) == []
    assert collector.work_to_do == -6_250

    collector.young_collection()

    # gc_collect_region(collecting, &survivors)
    assert [heap.is_freed(x) for x in (a, b)] == [True, True]
    assert heap.uncollected_garbage == 0
    # old_work += survivor_count; gc_list_merge_front(&survivors, old)
    assert collector.work_to_do == -6_250 + 2
    assert list(collector.visited_space) == [sys, held]
    # gc_list_merge(&young.nursery, collecting)
    assert collector.aging == [second_nursery]
    assert collector.nursery is not second_nursery
    assert list(collector.nursery) == []


def test_young_survivors_go_to_visiteds_front() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000, threshold1=2))
    heap = Heap(collector)
    old = heap.allocate()
    collector.visited_space.append(old)
    young = heap.allocate()

    collector.young_collection()
    collector.young_collection()

    assert list(collector.visited_space) == [heap.module_root, young, old]


def test_an_old_space_takes_objects_at_its_front_and_its_back() -> None:
    collector = IncrementalCollector()
    space = OldSpace(collector)
    space.extend([1, 2])
    space.merge_front([3, 4])
    space.append(5)
    space.merge_front([6])

    assert list(space) == [6, 3, 4, 1, 2, 5]
    assert (space.pop(), space.pop(0)) == (5, 6)
    # Moving an object to another space takes it out of this one.
    collector.nursery.append(1)
    assert list(space) == [3, 4, 2]
    space.append(3)
    assert list(space) == [4, 2, 3]
    assert [space.pop(0) for _ in range(3)] == [4, 2, 3]


def test_an_old_space_keeps_its_order_as_objects_pass_through_it() -> None:
    collector = IncrementalCollector()
    space = OldSpace(collector)
    for x in range(1_000):
        space.append(x)
        if x % 3:
            space.pop(0)

    assert list(space) == list(range(666, 1_000))
    assert len(space._lasts) < 2 * len(space) + 100


def test_the_budget_starts_at_the_initial_work_budget_in_simulated_objects() -> None:
    assert IncrementalCollector().work_to_do == -6_250
    # -1,000 real objects of 48 B: 46.875 kB, rounded down.
    constants = Constants(initial_work_budget=-1_000, real_object_size=48)
    assert IncrementalCollector(constants=constants).work_to_do == -47


def test_collections_alternate_from_a_young_one_and_young_ones_start_idle() -> None:
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

    # As the PEP's abstract and the reference branch order them.
    assert [counts.kind for counts in collector.counts] == ["young", "old"] * 6
    young = [counts for counts in collector.counts if counts.kind == "young"]
    # Five aging spaces, all empty at first; the sixth takes the first nursery,
    # sys with it.
    assert [(c.survived, c.freed, c.work) for c in young] == [(0, 0, 0)] * 5 + [
        (9, 2, 11)
    ]
    assert list(collector.visited_space) == [heap.module_root, *first]


class Recorded(IncrementalCollector):
    """An incremental collector whose budget starts at 0, so that old collections
    run within a short run. It notes the budget around each collection, and at each
    collection that ends a sweep the cyclic garbage wholly in the old generation."""

    def __init__(self, settings: CollectorSettings, constants: Constants) -> None:
        super().__init__(settings, constants)
        self.work_to_do = 0
        # Each collection's budget before and after, the sweeps it ended, and its
        # counts.
        self.budgets: list[tuple[int, int, int, CollectionCounts]] = []
        self.garbage_at_swaps: list[list[int]] = []
        # At each swap, what the last swap found that is still alive.
        self.left_by_sweeps: list[list[int]] = []

    @override
    def attach(self, heap: Heap) -> None:
        super().attach(heap)
        self.heap = heap

    @override
    def collect(self) -> None:
        before, sweeps = self.work_to_do, self.sweeps
        super().collect()
        ended = self.sweeps - sweeps
        self.budgets.append((before, self.work_to_do, ended, self.counts[-1]))
        if ended:
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
    st.lists(structure_parameters(own=False), max_size=2),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=1, max_value=6),
    constants(),
    st.lists(st.integers(min_value=0, max_value=600), max_size=4),
)
def test_a_run_keeps_the_incremental_collectors_invariants(
    churn: ChurnParameters,
    structures: list[StructureParameters],
    seed: int,
    threshold0: int,
    threshold1: int,
    constants: Constants,
    stops: list[int],
) -> None:
    """The workloads' garbage never holds other garbage, so each sweep frees the
    cyclic garbage wholly in the old generation when it starts, young objects
    joining it or not. A reader's own
    shape can hold one cycle from another: an increment that takes the held cycle
    first leaves it in visited, still held, and the next sweep frees it."""
    settings = CollectorSettings(threshold0=threshold0, threshold1=threshold1)
    collector = Recorded(settings, constants)
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

    for before, after, ended, counts in collector.budgets:
        if counts.kind == "young":
            assert after == before + counts.survived
            continue
        # Settled once, after the collection; a swap at its end sets it to 0.
        examined = counts.survived + counts.freed
        credit = constants.freed_credit * counts.freed
        settled = before - counts.marked - examined + credit
        assert after in (0, settled) if ended else after == settled
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

    # It marks sys and m, sees held survive and frees both cycles.
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


def test_after_a_full_collection_the_next_old_collection_swaps_before_marking() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    held = heap.allocate()
    collector.collect_full("full")
    # The full collection leaves visited as old[1].
    assert collector.visited_index == 1
    collector.work_to_do = 1

    collector.old_collection()

    assert list(collector.visited_space) == [sys]
    assert list(collector.pending_space) == [held]
    assert list(collector.reachable) == []
    assert collector.visited_index == 0
    assert collector.work_to_do == 0
    assert collector.sweeps == 1


def test_an_old_collection_follows_the_branch_line_by_line() -> None:
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
    # The old generation, least recently scanned first. sys stays young.
    collector.pending_space.extend([m1, m2, held, a, b])
    collector.work_to_do = 10
    collector.young_next = False

    collector.collect()

    # Each increment starts at pending's last object. [b, a] is cyclic garbage,
    # then [held], [m2] and [m1] survive, each at visited's front: 5 examined.
    # pending runs empty, and old_work settles once: 10 - 5 + 2 * 2.
    # Then the spaces swap. Visited is old[1] now, so young objects carry
    # pending's tag, and sys, still young, goes on reachable.
    assert [heap.is_freed(x) for x in (a, b)] == [True, True]
    assert list(collector.pending_space) == [m1, m2, held]
    assert list(collector.visited_space) == []
    assert list(collector.reachable) == [sys]
    assert collector.visited_index == 1
    assert collector.work_to_do == 0
    assert collector.counts == [CollectionCounts("old", 0, 3, 2)]


@pytest.mark.parametrize("credit", [0, 2, 3])
def test_an_old_collection_credits_what_its_increments_free_once_it_ends(
    credit: int,
) -> None:
    settings = CollectorSettings(threshold0=1_000)
    collector = IncrementalCollector(settings, Constants(freed_credit=credit))
    heap = Heap(collector)
    a, b = heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(a, leaves_unreachable=2)
    held = [heap.allocate() for _ in range(10)]  # their allocating frames hold them
    collector.pending_space.extend([*held, a, b])
    collector.work_to_do = 3
    collector.young_next = False

    collector.collect()

    # The increment [b, a] frees both and the next one examines a held object,
    # which spends the budget whatever the credit. The credit goes to the next
    # old collection.
    assert [heap.is_freed(x) for x in (a, b)] == [True, True]
    assert collector.counts == [CollectionCounts("old", 0, 1, 2)]
    assert collector.work_to_do == credit * 2


def test_marking_leaves_young_objects_while_visited_is_old_0() -> None:
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
    collector.reachable.append(sys)
    collector.work_to_do = 2

    collector.old_collection()

    # scan_reachable(2) moves sys and m1, leaves m2 on reachable, and leaves the
    # young object where it is.
    assert list(collector.visited_space) == [sys, m1]
    assert list(collector.reachable) == [m2]
    assert list(collector.nursery) == [young]

    collector.work_to_do = 1
    collector.old_collection()

    # m2 empties reachable and pending both, so the spaces swap, and sys goes from
    # the new pending to reachable.
    assert list(collector.pending_space) == [m1, m2]
    assert list(collector.reachable) == [sys]
    assert collector.sweeps == 1


def test_marking_takes_young_objects_while_visited_is_old_1() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    m1, young, young_too = heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(sys, m1)
    heap.link(sys, young)
    heap.link(young, young_too)
    for x in (m1, young, young_too):
        heap.let_go_frame_root(x)
    collector.pending_space.append(m1)
    collector.reachable.append(sys)
    collector.visited_index = 1
    collector.work_to_do = 3
    collector.young_next = False

    collector.collect()

    # Young objects carry old[0]'s tag, pending's while visited is old[1]: marking
    # takes them out of the young generation, unexamined.
    assert list(collector.visited_space) == [sys, m1, young]
    assert list(collector.reachable) == [young_too]
    assert list(collector.nursery) == []
    assert collector.counts == [CollectionCounts("old", 3, 0, 0)]


def test_an_increment_takes_young_objects_while_visited_is_old_1() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    old, young = heap.allocate(), heap.allocate()
    heap.link(old, young)
    heap.let_go_frame_root(young)
    collector.pending_space.extend([heap.allocate(), old])
    collector.visited_index = 1
    collector.work_to_do = 1
    collector.young_next = False

    collector.collect()

    assert collector.counts == [CollectionCounts("old", 0, 2, 0)]
    assert young not in collector.nursery
    assert collector.work_to_do == -1


def test_the_next_old_collection_resumes_where_the_budget_ran_out() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    p, q, r = heap.allocate(), heap.allocate(), heap.allocate()  # frames hold them
    collector.pending_space.extend([p, q, r])
    collector.work_to_do = 2
    collector.young_next = False

    collector.collect()

    # Increments take pending's last objects, and each one's survivors go to
    # visited's front.
    assert list(collector.visited_space) == [q, r]
    assert list(collector.pending_space) == [p]
    assert collector.work_to_do == 0

    collector.collect()  # a young collection, with nothing to collect
    collector.work_to_do = 1
    collector.collect()

    # p empties pending, so the spaces swap and a sweep ends.
    assert list(collector.pending_space) == [p, q, r]
    assert collector.sweeps == 1
    assert collector.counts == [
        CollectionCounts("old", 0, 2, 0),
        CollectionCounts("young", 0, 0, 0),
        CollectionCounts("old", 0, 1, 0),
    ]


def test_an_old_collection_without_a_positive_budget_is_idle() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    x = heap.allocate()
    collector.pending_space.append(x)
    collector.work_to_do = 0
    collector.young_next = False

    collector.collect()

    assert list(collector.reachable) == []
    assert list(collector.pending_space) == [x]
    assert collector.counts == [CollectionCounts("old", 0, 0, 0)]


def test_a_swap_that_leaves_sys_visited_marks_nothing_and_swaps_back() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    collector.visited_index = 1
    collector.work_to_do = 1
    collector.young_next = False

    collector.collect()

    # The swap makes old[0] visited, whose tag sys carries while it is young, so
    # nothing goes on reachable. Pending stays empty, the budget stays unspent, and
    # the spaces swap back, which puts sys on reachable.
    assert collector.counts == [CollectionCounts("old", 0, 0, 0)]
    assert collector.sweeps == 2
    assert collector.visited_index == 1
    assert list(collector.reachable) == [sys]
    assert collector.work_to_do == 0


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
    # The older cycle last, so that the first increment takes it.
    collector.pending_space.extend([b1, b2, a1, a2])
    collector.work_to_do = 100

    collector.old_collection()

    # The increment from a2 holds a2 and a1 alone, and b1 holds a1 from outside it.
    assert [heap.is_freed(x) for x in (a1, a2, b1, b2)] == [False, False, True, True]
    assert sorted(collector.pending_space) == sorted([a1, a2])
    assert heap.uncollected_garbage == 2

    collector.work_to_do = 100
    collector.old_collection()

    assert [heap.is_freed(x) for x in (a1, a2)] == [True, True]
    assert heap.uncollected_garbage == 0


@pytest.mark.parametrize("threshold1", [0, -1])
def test_a_threshold1_below_1_runs_as_1(threshold1: int) -> None:
    # As the reference branch's gc.set_threshold() clamps it: one aging space.
    collector = IncrementalCollector(CollectorSettings(threshold1=threshold1))
    heap = Heap(collector)
    heap.allocate()

    collector.collect()
    collector.collect()

    assert len(collector.aging) == 1
    assert [record.kind for record in collector.records] == ["young", "old"]


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

    # Spaces: nursery, aging, pending, visited (reachable among them). sys starts
    # young and ages with the rest.
    idle = (0, 0, 0, -6_250, 0)
    assert collector.records == [
        Record(5, "young", *idle, (4, 0, 0, 0), (0, 4, 0, 0), 2, 2),
        Record(10, "old", *idle, (0, 4, 0, 0), (0, 4, 0, 0), 2, 2),
        Record(15, "young", 0, 2, 2, -6_248, 0, (0, 4, 0, 0), (0, 0, 0, 2), 2, 2),
        Record(20, "old", 0, 0, 0, -6_248, 0, (0, 0, 0, 2), (0, 0, 0, 2), 2, 2),
    ]


def test_an_old_collections_record_carries_the_budget_and_the_sweep() -> None:
    collector = IncrementalCollector(CollectorSettings(threshold0=5))
    heap = Heap(collector)
    collector.work_to_do = 10
    collector.young_next = False

    for _ in range(6):
        heap.allocate_unseen()

    # pending and reachable are empty, so the spaces swap and a sweep ends. sys,
    # young and so pending's tag now, goes on reachable, and marking takes it
    # (10 - 1). Both are empty again, so the spaces swap back, a second sweep ends
    # and the budget goes to 0.
    assert collector.records == [
        Record(5, "old", 1, 0, 0, 0, 2, (1, 0, 0, 0), (0, 0, 0, 1), 1, 1)
    ]
