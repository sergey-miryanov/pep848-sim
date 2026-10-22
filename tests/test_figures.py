from functools import reduce

from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import Collector, CollectorSettings, Record
from pep848_sim.run import run
from pep848_sim.widget.figures import Figures
from pep848_sim.workload import WorkloadParameters
from test_run import COLLECTORS, collector_settings, records, workloads


def record(
    clock: int = 2_000,
    kind: str = "young",
    marked: int = 0,
    survived: int = 0,
    freed: int = 0,
    sweep: int = 0,
    spaces_before: tuple[int, ...] = (0,),
    spaces_after: tuple[int, ...] = (0,),
    reachable_before: int = 0,
    reachable_after: int = 0,
) -> Record:
    """A record of a collection, by default with an empty heap around it."""
    return Record(
        clock,
        kind,
        marked,
        survived,
        freed,
        0,
        sweep,
        spaces_before,
        spaces_after,
        reachable_before,
        reachable_after,
    )


def test_peak_work_is_the_most_work_one_collection_did() -> None:
    records = [
        record(marked=30, survived=4, freed=5),
        record(survived=50),
        record(survived=20, freed=20),
    ]

    assert Figures().add(records).peak_work == 50


def test_peak_uncollected_garbage_is_the_most_a_collection_started_with() -> None:
    # The first collection starts with 60 - 45 = 15 kB of uncollected garbage and
    # frees 13. The second starts with 9 and frees none, so it ends with more
    # than the first: 9 against 2.
    records = [
        record(
            freed=13,
            spaces_before=(10, 20, 30),
            reachable_before=45,
            spaces_after=(0, 20, 27),
            reachable_after=45,
        ),
        record(
            spaces_before=(0, 30, 29),
            reachable_before=50,
            spaces_after=(0, 0, 59),
            reachable_after=50,
        ),
    ]

    assert Figures().add(records).peak_uncollected_garbage == 15


def test_work_per_mb_divides_the_runs_work_by_the_mb_allocated_so_far() -> None:
    # 39 + 50 + 40 = 129 objects of work over the 6 MB allocated by the last
    # collection.
    records = [
        record(clock=2_000, marked=30, survived=4, freed=5),
        record(clock=4_000, survived=50),
        record(clock=6_000, survived=20, freed=20),
    ]

    assert Figures().add(records).work_per_mb == 21.5


def test_yield_is_the_share_of_the_objects_the_run_examined_that_it_freed() -> None:
    # 20 freed of 100 examined; the 30 marked were never examined.
    records = [
        record(marked=30, survived=10, freed=5),
        record(survived=50),
        record(survived=20, freed=15),
    ]

    assert Figures().add(records).yield_ == 0.2


def test_a_run_that_has_examined_nothing_has_no_yield() -> None:
    records = [record(kind="young"), record(kind="old", marked=40)]

    assert Figures().add(records).yield_ is None


def test_collections_counts_every_collection_idle_ones_included() -> None:
    records = [
        record(kind="young"),
        record(kind="old", marked=40),
        record(kind="young", survived=3),
    ]

    assert Figures().add(records).collections == 3


def test_sweeps_are_the_sweeps_the_incremental_run_has_ended() -> None:
    # Each record holds the sweeps ended by the time its collection did.
    records = [
        record(kind="old", sweep=0),
        record(kind="old", sweep=1),
        record(kind="young", sweep=1),
        record(kind="old", sweep=2),
    ]

    assert Figures().add(records).sweeps == 2


def test_gen_2_collections_are_the_legacy_runs_collections_of_the_whole_heap() -> None:
    records = [
        record(kind="gen 0"),
        record(kind="gen 1"),
        record(kind="gen 2"),
        record(kind="gen 0"),
        record(kind="gen 2"),
    ]

    assert Figures().add(records).gen2_collections == 2


@given(
    workloads(),
    st.sampled_from(COLLECTORS),
    collector_settings(),
    st.integers(min_value=0, max_value=600),
    st.integers(min_value=1, max_value=5),
)
def test_figures_taken_part_by_part_match_those_of_the_whole_run(
    parameters: WorkloadParameters,
    collector: type[Collector],
    settings: CollectorSettings,
    run_length: int,
    every: int,
) -> None:
    parts = list(run(parameters, collector, settings, run_length, every))

    assert reduce(Figures.add, parts, Figures()) == Figures().add(records(parts))


def test_the_row_holds_the_figures_in_the_order_the_widget_shows_them() -> None:
    # A gen 0 collection examines the nursery's 8 objects and frees 2. A gen 2
    # collection examines all 12 and frees 3, having started with 12 - 8 = 4
    # unreachable.
    records = [
        record(
            clock=2_000,
            kind="gen 0",
            survived=6,
            freed=2,
            spaces_before=(8, 0, 0),
            reachable_before=5,
            spaces_after=(0, 6, 0),
            reachable_after=5,
        ),
        record(
            clock=4_000,
            kind="gen 2",
            survived=9,
            freed=3,
            spaces_before=(6, 6, 0),
            reachable_before=8,
            spaces_after=(0, 0, 9),
            reachable_after=8,
        ),
    ]

    # Peak work, peak uncollected garbage, work per MB (20 over 4 MB), yield
    # (5 of 20), collections, sweeps and gen 2 collections.
    assert Figures().add(records).row() == (12, 4, 5.0, 0.25, 2, 0, 1)
