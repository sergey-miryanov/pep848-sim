import pytest

from benchmarks import Collection, Kind, Tally
from pep848_sim.collectors.collector import Constants
from plot_presets import PANELS, collections, columns, points
from test_figures import record

# A collection that examined 100 real objects and freed 10.
ONE = Tally(1, 100, 10)


def collection(
    generation: int = 0,
    gained: Tally = ONE,
    increment_size: int | None = None,
    old_work: int | None = None,
    shutdown: bool = False,
) -> Collection:
    """One of a worker's collections, by default an automatic young one."""
    kind: Kind = "explicit" if shutdown else "automatic"
    return Collection(generation, kind, gained, increment_size, old_work, shutdown)


def test_a_runs_records_become_collections_in_real_objects() -> None:
    records = [
        record(kind="young", survived=3, freed=1)._replace(work_to_do=-50),
        record(kind="old", marked=9, survived=5)._replace(work_to_do=20),
        record(kind="full", survived=6, freed=2),
    ]

    # 16 real objects to a simulated one. The budget before the first record is
    # the initial one, and before each later one the record before's.
    assert collections(records, Constants()) == [
        Collection(0, "automatic", Tally(1, 64, 16), 64, -100_000, False),
        Collection(1, "automatic", Tally(1, 80, 0), 224, -800, False),
        Collection(2, "explicit", Tally(1, 128, 32), 128, 320, False),
    ]


def test_shutdowns_records_are_marked_as_shutdowns() -> None:
    [shutdown] = collections([record(kind="shutdown", freed=4)], Constants())

    assert shutdown.shutdown


def test_collections_count_real_objects_by_the_runs_constants() -> None:
    [young] = collections(
        [record(survived=3, freed=1)], Constants(real_object_size=128)
    )

    assert young.gained == Tally(1, 32, 8)


def test_a_point_stands_at_its_collections_number_in_the_worker() -> None:
    worker = [
        collection(),
        # A record gcmon lost folds into this row.
        collection(gained=Tally(2, 300, 30)),
        collection(generation=1),
    ]

    assert [point["n"] for point in points(worker, "legacy")] == [1, 3, 4]


def test_a_row_that_folds_lost_collections_draws_their_average() -> None:
    [point] = points([collection(gained=Tally(2, 300, 30))], "legacy")

    assert (point["examined"], point["freed"]) == (150, 15)


def test_a_row_that_gains_no_collection_draws_nothing_examined_or_freed() -> None:
    [point] = points([collection(gained=Tally())], "legacy")

    assert "examined" not in point
    assert "freed" not in point


def test_the_running_yield_runs_over_each_panel_alone() -> None:
    worker = [
        collection(gained=Tally(1, 100, 50)),
        collection(generation=1, gained=Tally(1, 1000, 0)),
        collection(gained=Tally(1, 300, 0)),
    ]

    assert [(p["panel"], p.get("yield")) for p in points(worker, "legacy")] == [
        ("gen 0 automatic", 0.5),
        ("gen 1 automatic", 0),
        ("gen 0 automatic", 0.125),
    ]


def test_no_running_yield_until_a_panel_has_examined_an_object() -> None:
    [point] = points([collection(gained=Tally(1, 0, 0))], "legacy")

    assert "yield" not in point


def test_shutdowns_collections_count_but_draw_nothing() -> None:
    worker = [collection(), collection(shutdown=True), collection()]

    assert [point["n"] for point in points(worker, "legacy")] == [1, 3]


@pytest.mark.parametrize(
    ("collector", "drawn"),
    [("incremental", [False, True, True]), ("legacy", [False, False, True])],
)
def test_only_old_collections_draw_their_work(
    collector: str, drawn: list[bool]
) -> None:
    worker = [collection(generation=g, increment_size=0) for g in (0, 1, 2)]

    assert ["work" in point for point in points(worker, collector)] == drawn


def test_a_row_without_its_work_draws_none() -> None:
    [point] = points([collection(generation=2)], "legacy")

    assert "work" not in point


def test_only_the_incremental_collector_draws_its_budget() -> None:
    worker = [collection(old_work=-100_000)]

    assert points(worker, "incremental")[0]["budget"] == -100_000
    assert "budget" not in points(worker, "legacy")[0]


def test_the_panels_are_every_generation_and_kind_a_collection_files_in() -> None:
    assert PANELS == [
        "gen 0 automatic",
        "gen 1 automatic",
        "gen 2 automatic",
        "gen 2 explicit",
    ]


def test_columns_hold_a_series_each_with_null_where_a_point_has_none() -> None:
    drawn = points(
        [collection(), collection(generation=2, increment_size=500)], "legacy"
    )

    # Panels by their place in PANELS.
    assert columns(drawn) == {
        "n": [1, 2],
        "panel": [0, 2],
        "examined": [100, 100],
        "freed": [10, 10],
        "yield": [0.1, 0.1],
        "work": [None, 500],
    }


def test_a_series_no_point_has_takes_no_column() -> None:
    drawn = points([collection()], "legacy")

    assert set(columns(drawn)) == {"n", "panel", "examined", "freed", "yield"}


def test_a_mean_keeps_four_significant_digits_and_a_whole_one_its_int() -> None:
    drawn = points([collection(gained=Tally(3, 100, 30))], "legacy")

    assert columns(drawn)["examined"] == [33.33]
    assert columns(drawn)["freed"] == [10]
