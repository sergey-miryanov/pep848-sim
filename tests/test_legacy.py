from typing import override

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collector import CollectionCounts, CollectorSettings, Record
from pep848_sim.heap import Heap
from pep848_sim.legacy import LegacyCollector
from pep848_sim.structures import StructureParameters
from pep848_sim.workload import ChurnParameters, Workload, WorkloadParameters
from test_heap import reachable
from test_workload import churn_parameters, structure_parameters


def test_each_generations_collection_follows_the_reference_branch() -> None:
    collector = LegacyCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    sys = heap.module_root
    held = heap.allocate()  # its allocating frame holds it
    a, b = heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(a, leaves_unreachable=2)

    # Gen 0: old[0].count++, and the nursery's survivors go to aging[0].
    collector.collect_generation0()

    assert [heap.is_freed(x) for x in (a, b)] == [True, True]
    assert list(collector.aging) == [sys, held]
    assert list(collector.nursery) == []
    assert (collector.count0, collector.count1) == (1, 0)

    # Gen 1: the nursery joins aging[0], whose survivors go to old[0] and count as
    # long-lived objects awaiting a gen 2 collection.
    c = heap.allocate()
    collector.collect_generation1()

    assert list(collector.old) == [sys, held, c]
    assert list(collector.aging) == list(collector.nursery) == []
    assert (collector.count0, collector.count1) == (0, 1)
    assert collector.long_lived_pending == 3

    # Gen 2: the nursery, then aging[0], join old[0], collected in place.
    heap.link(held, c)
    heap.link(c, held)
    x = heap.allocate()
    collector.collect_generation0()
    n = heap.allocate()
    heap.let_go_frame_root(held)
    heap.let_go_frame_root(c, leaves_unreachable=2)
    collector.collect_generation2()

    assert [heap.is_freed(x) for x in (held, c)] == [True, True]
    assert list(collector.old) == [sys, n, x]
    assert list(collector.aging) == list(collector.nursery) == []
    assert (collector.count0, collector.count1) == (0, 0)
    assert (collector.long_lived_pending, collector.long_lived_total) == (0, 3)
    assert collector.counts == [
        CollectionCounts("gen 0", 0, 2, 2),
        CollectionCounts("gen 1", 0, 3, 0),
        CollectionCounts("gen 0", 0, 1, 0),
        CollectionCounts("gen 2", 0, 3, 2),
    ]


@pytest.mark.parametrize(
    ("count0", "count1", "pending", "total", "generation"),
    [
        (10, 10, 0, 0, 0),  # neither count is over its threshold
        (11, 10, 0, 0, 1),
        (0, 11, 0, 0, 2),
        (11, 11, 2, 8, 2),  # pending reaches a quarter of the total
        (11, 11, 1, 8, 1),  # it does not, so gen 2 waits and gen 1 runs
        (0, 11, 1, 8, 0),
    ],
)
def test_the_generation_chosen_follows_the_counts_and_the_long_lived_ratio(
    count0: int, count1: int, pending: int, total: int, generation: int
) -> None:
    collector = LegacyCollector()
    collector.count0, collector.count1 = count0, count1
    collector.long_lived_pending, collector.long_lived_total = pending, total

    assert collector.select_generation() == generation


def test_with_the_default_thresholds_gen_1_comes_12th_and_gen_2_133rd() -> None:
    collector = LegacyCollector(CollectorSettings(threshold0=1))
    heap = Heap(collector)

    # A collection at the start of each kB after the first: 133 of them.
    for _ in range(134):
        heap.allocate_unseen()

    rounds = (["gen 0"] * 11 + ["gen 1"]) * 11
    assert [counts.kind for counts in collector.counts] == [*rounds, "gen 2"]


class Recorded(LegacyCollector):
    """A legacy collector that notes the uncollected garbage each gen 2 leaves."""

    def __init__(self, settings: CollectorSettings) -> None:
        super().__init__(settings)
        self.left_by_gen2: list[int] = []

    @override
    def attach(self, heap: Heap) -> None:
        super().attach(heap)
        self.heap = heap

    @override
    def collect_generation2(self) -> None:
        super().collect_generation2()
        self.left_by_gen2.append(self.heap.uncollected_garbage)


@given(
    churn_parameters(),
    st.lists(structure_parameters(), max_size=2),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=0, max_value=3),
    st.integers(min_value=0, max_value=3),
    st.lists(st.integers(min_value=0, max_value=600), max_size=4),
)
def test_a_run_keeps_the_legacy_collectors_invariants(
    churn: ChurnParameters,
    structures: list[StructureParameters],
    seed: int,
    threshold0: int,
    threshold1: int,
    threshold2: int,
    stops: list[int],
) -> None:
    settings = CollectorSettings(threshold0, threshold1, threshold2)
    collector = Recorded(settings)
    heap = Heap(collector)
    workload = Workload(heap, WorkloadParameters(churn, tuple(structures), seed))

    for stop in sorted(stops):
        workload.run_to(stop)

        spaces = [collector.nursery, collector.aging, collector.old]
        placed = [x for space in spaces for x in space]
        assert len(placed) == len(set(placed)) == len(heap)
        assert [x for x in placed if heap.is_freed(x)] == []
        reached = reachable(heap)
        assert [x for x in reached if heap.is_freed(x)] == []
        assert heap.uncollected_garbage == len(set(placed) - reached)

    # A gen 2 collection takes the whole heap.
    assert [left for left in collector.left_by_gen2 if left] == []


def test_a_legacy_record_holds_no_budget_and_no_sweep() -> None:
    collector = LegacyCollector(
        CollectorSettings(threshold0=1, threshold1=0, threshold2=0)
    )
    heap = Heap(collector)

    for _ in range(4):
        heap.allocate_unseen()

    # Spaces: nursery, aging, old. Only sys is alive, and it moves on with each.
    assert collector.records == [
        Record(1, "gen 0", 0, 1, 0, 0, 0, (1, 0, 0), (0, 1, 0), 1, 1),
        Record(2, "gen 1", 0, 1, 0, 0, 0, (0, 1, 0), (0, 0, 1), 1, 1),
        Record(3, "gen 2", 0, 1, 0, 0, 0, (0, 0, 1), (0, 0, 1), 1, 1),
    ]
