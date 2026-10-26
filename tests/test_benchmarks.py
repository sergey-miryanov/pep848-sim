from csv import DictReader
from dataclasses import astuple
from pathlib import Path

import pytest

from benchmarks import DATA, FILES, Benchmark, Tally, load, load_data
from pep848_sim.collectors.collector import CollectorSettings

HEADER = ",".join(
    (
        "benchmark",
        "pid",
        "pid_epoch",
        "calibration",
        "ts",
        "generation",
        "auto_collect",
        "reason",
        "collections",
        "candidates",
        "collected",
    )
)

FIVE = {
    "async_tree_io_tg",
    "connected_components",
    "create_gc_cycles",
    "json_loads",
    "xml_etree_parse",
}


def write(path: Path, *rows: str) -> Path:
    path.write_text("\n".join((HEADER, *rows)) + "\n", newline="")
    return path


def test_a_row_counts_what_its_totals_gained_since_the_last_row_of_its_generation(
    tmp_path: Path,
) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
        "json_loads,7,1,0,200,1,1,0,1,500,0",
        "json_loads,7,1,0,300,0,1,0,2,250,40",
    )

    assert load(csv) == {
        "json_loads": Benchmark(
            workers=1,
            tallies={
                (0, "automatic"): Tally(collections=2, candidates=250, collected=40),
                (1, "automatic"): Tally(collections=1, candidates=500, collected=0),
            },
            first_examined=100,
        )
    }


def test_a_lost_record_folds_into_the_next_row_of_its_generation(
    tmp_path: Path,
) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "connected_components,7,1,0,100,2,0,2,1,1000,10",
        # Two collections since the last row: the one lost was explicit, but its
        # counts go where the row read goes.
        "connected_components,7,1,0,200,2,1,0,3,3500,710",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {
        (2, "explicit"): Tally(1, 1000, 10),
        (2, "automatic"): Tally(2, 2500, 700),
    }


def test_a_workers_rows_count_in_the_order_of_their_ts(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,300,0,1,0,2,250,40",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {(0, "automatic"): Tally(2, 250, 40)}


def test_each_worker_keeps_its_own_running_totals(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
        "json_loads,8,1,0,150,0,1,0,1,300,30",
        "json_loads,7,1,0,200,0,1,0,2,250,40",
    )

    [benchmark] = load(csv).values()

    assert benchmark == Benchmark(2, {(0, "automatic"): Tally(3, 550, 70)}, 200)


def test_a_worker_is_its_pid_and_its_pid_epoch(tmp_path: Path) -> None:
    # The system gave pid 7 to a second worker once the first had ended.
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
        "json_loads,7,2,0,150,0,1,0,1,300,30",
    )

    [benchmark] = load(csv).values()

    assert benchmark == Benchmark(2, {(0, "automatic"): Tally(2, 400, 40)}, 200)


def test_leaves_the_calibration_workers_out(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,6,1,1,50,0,1,0,1,900,90",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
    )

    assert load(csv) == {
        "json_loads": Benchmark(1, {(0, "automatic"): Tally(1, 100, 10)}, 100)
    }


def test_leaves_out_the_processes_with_no_benchmark_name(tmp_path: Path) -> None:
    # pyperformance's own processes, which run no benchmark.
    csv = write(
        tmp_path / "trace.csv",
        ",6,1,0,50,0,1,0,1,900,90",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
    )

    assert set(load(csv)) == {"json_loads"}


def test_keeps_each_benchmark_apart(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "xml_etree_parse,7,1,0,100,0,1,0,1,100,10",
        "create_gc_cycles,8,1,0,100,0,1,0,1,300,30",
    )

    assert load(csv) == {
        "create_gc_cycles": Benchmark(1, {(0, "automatic"): Tally(1, 300, 30)}, 300),
        "xml_etree_parse": Benchmark(1, {(0, "automatic"): Tally(1, 100, 10)}, 100),
    }


def test_shutdowns_collections_set_no_target(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "create_gc_cycles,7,1,0,100,0,1,0,1,100,1",
        # Two gc.collect() calls.
        "create_gc_cycles,7,1,0,200,2,0,2,1,500,50",
        "create_gc_cycles,7,1,0,300,2,0,2,2,900,150",
        # _Py_Finalize's, under gc.collect()'s reason, then finalize_modules' two.
        "create_gc_cycles,7,1,0,400,2,0,2,3,1300,151",
        "create_gc_cycles,7,1,0,500,2,0,1,4,1400,240",
        "create_gc_cycles,7,1,0,600,2,0,1,5,1400,240",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {
        (0, "automatic"): Tally(1, 100, 1),
        (2, "explicit"): Tally(2, 900, 150),
    }


def test_a_workers_last_manual_row_is_shutdowns_where_gcmon_lost_the_rest(
    tmp_path: Path,
) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
        "json_loads,7,1,0,200,2,0,2,1,400,4",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {(0, "automatic"): Tally(1, 100, 10)}


def test_where_gcmon_lost_all_of_shutdowns_rows_the_last_call_goes_in_their_place(
    tmp_path: Path,
) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "create_gc_cycles,7,1,0,200,2,0,2,1,500,50",
        "create_gc_cycles,7,1,0,300,2,0,2,2,900,150",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {(2, "explicit"): Tally(1, 500, 50)}


def test_a_manual_row_an_automatic_collection_follows_is_a_call(
    tmp_path: Path,
) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,100,2,0,2,1,400,4",
        "json_loads,7,1,0,200,0,1,0,1,100,10",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {
        (2, "explicit"): Tally(1, 400, 4),
        (0, "automatic"): Tally(1, 100, 10),
    }


def test_the_first_collections_candidates_are_averaged_over_the_workers(
    tmp_path: Path,
) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,200,0,1,0,2,250,40",
        "json_loads,7,1,0,100,0,1,0,1,100,10",
        "json_loads,8,1,0,150,0,1,0,1,300,30",
    )

    [benchmark] = load(csv).values()

    assert benchmark.first_examined == 200


def test_a_worker_whose_first_collection_gcmon_lost_gives_none(
    tmp_path: Path,
) -> None:
    csv = write(tmp_path / "trace.csv", "json_loads,7,1,0,100,0,1,0,2,250,40")

    [benchmark] = load(csv).values()

    assert benchmark.first_examined is None


def test_running_totals_that_fall_are_an_error(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,1,0,100,0,1,0,2,250,40",
        "json_loads,7,1,0,200,0,1,0,3,240,40",
    )

    with pytest.raises(ValueError, match="json_loads worker 7's generation 0 totals"):
        load(csv)


def test_yield_is_collected_over_candidates() -> None:
    assert Tally(collections=4, candidates=200, collected=50).yield_ == 0.25


def test_yield_is_none_until_a_collection_had_a_candidate() -> None:
    assert Tally(collections=4).yield_ is None


def test_a_collection_examines_its_candidates_on_average() -> None:
    assert Tally(collections=4, candidates=200, collected=50).examined_each == 50
    assert Tally().examined_each is None


def test_per_worker_is_a_generation_and_kinds_collections_over_the_workers() -> None:
    benchmark = Benchmark(4, {(2, "explicit"): Tally(10, 0, 0)})

    assert benchmark.per_worker(2, "explicit") == 2.5
    assert benchmark.per_worker(0, "automatic") == 0


def test_the_data_holds_the_five_benchmarks_under_both_collectors() -> None:
    data = load_data()

    assert set(data) == {"incremental", "legacy"}
    for benchmarks in data.values():
        assert set(benchmarks) >= FIVE
        for name in FIVE:
            assert benchmarks[name].workers > 0
            assert (0, "automatic") in benchmarks[name].tallies


# gcmon's names for the collectors, in its gc_type column.
GC_TYPES = {"legacy": "1", "incremental": "2"}


@pytest.mark.parametrize("collector", FILES)
def test_each_file_holds_its_collector_at_the_peps_thresholds(collector: str) -> None:
    with (DATA / FILES[collector]).open(newline="", encoding="utf-8") as file:
        rows = list(DictReader(file))

    assert {row["gc_type"] for row in rows} == {GC_TYPES[collector]}
    thresholds = {tuple(int(row[f"threshold{i}"]) for i in range(3)) for row in rows}
    assert thresholds == {astuple(CollectorSettings())}
