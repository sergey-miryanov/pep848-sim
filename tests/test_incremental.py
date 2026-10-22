from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collector import CollectorSettings
from pep848_sim.heap import Heap
from pep848_sim.incremental import IncrementalCollector
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


@given(
    churn_parameters(),
    st.lists(structure_parameters(), max_size=2),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=1, max_value=6),
    st.lists(st.integers(min_value=0, max_value=600), max_size=4),
)
def test_a_run_keeps_each_alive_object_in_one_space_and_frees_none_reachable(
    churn: ChurnParameters,
    structures: list[StructureParameters],
    seed: int,
    threshold0: int,
    threshold1: int,
    stops: list[int],
) -> None:
    settings = CollectorSettings(threshold0=threshold0, threshold1=threshold1)
    collector = IncrementalCollector(settings)
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
