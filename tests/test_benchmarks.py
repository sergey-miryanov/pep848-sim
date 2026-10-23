import json
from pathlib import Path

import pytest

from benchmarks import Benchmark, Tally, load, load_data, mock

HEADER = ",".join(
    (
        "benchmark",
        "worker",
        "calibration",
        "ts",
        "generation",
        "auto_collect",
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
        "json_loads,7,0,100,0,1,1,100,10",
        "json_loads,7,0,200,1,1,1,500,0",
        "json_loads,7,0,300,0,1,2,250,40",
    )

    assert load(csv) == {
        "json_loads": Benchmark(
            workers=1,
            tallies={
                (0, "automatic"): Tally(collections=2, candidates=250, collected=40),
                (1, "automatic"): Tally(collections=1, candidates=500, collected=0),
            },
        )
    }


def test_a_lost_record_folds_into_the_next_row_of_its_generation(
    tmp_path: Path,
) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "connected_components,7,0,100,2,0,1,1000,10",
        # Two collections since the last row: the one lost was explicit, but its
        # counts go where the row read goes.
        "connected_components,7,0,200,2,1,3,3500,710",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {
        (2, "explicit"): Tally(1, 1000, 10),
        (2, "automatic"): Tally(2, 2500, 700),
    }


def test_a_workers_rows_count_in_the_order_of_their_ts(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,0,300,0,1,2,250,40",
        "json_loads,7,0,100,0,1,1,100,10",
    )

    [benchmark] = load(csv).values()

    assert benchmark.tallies == {(0, "automatic"): Tally(2, 250, 40)}


def test_each_worker_keeps_its_own_running_totals(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,0,100,0,1,1,100,10",
        "json_loads,8,0,150,0,1,1,300,30",
        "json_loads,7,0,200,0,1,2,250,40",
    )

    [benchmark] = load(csv).values()

    assert benchmark == Benchmark(2, {(0, "automatic"): Tally(3, 550, 70)})


def test_leaves_the_calibration_workers_out(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,6,1,50,0,1,1,900,90",
        "json_loads,7,0,100,0,1,1,100,10",
    )

    assert load(csv) == {
        "json_loads": Benchmark(1, {(0, "automatic"): Tally(1, 100, 10)})
    }


def test_keeps_each_benchmark_apart(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "xml_etree_parse,7,0,100,0,1,1,100,10",
        "create_gc_cycles,8,0,100,2,0,1,300,30",
    )

    assert load(csv) == {
        "create_gc_cycles": Benchmark(1, {(2, "explicit"): Tally(1, 300, 30)}),
        "xml_etree_parse": Benchmark(1, {(0, "automatic"): Tally(1, 100, 10)}),
    }


def test_the_first_heap_is_each_workers_first_heap_size_averaged(
    tmp_path: Path,
) -> None:
    csv = tmp_path / "trace.csv"
    csv.write_text(
        "benchmark,worker,calibration,ts,generation,auto_collect,collections,"
        "candidates,collected,heap_size\n"
        "json_loads,7,0,200,0,1,2,250,40,1500\n"
        "json_loads,7,0,100,0,1,1,100,10,1000\n"
        "json_loads,8,0,150,0,1,1,300,30,2000\n",
        newline="",
    )

    [benchmark] = load(csv).values()

    assert benchmark.first_heap == 1500


def test_without_heap_sizes_there_is_no_first_heap(tmp_path: Path) -> None:
    csv = write(tmp_path / "trace.csv", "json_loads,7,0,100,0,1,1,100,10")

    [benchmark] = load(csv).values()

    assert benchmark.first_heap is None


@pytest.mark.parametrize(
    ("marks", "mocked"),
    [((True, True), True), ((False, True), True), ((False, False), False)],
)
def test_the_data_is_mock_if_any_metadata_says_so(
    tmp_path: Path, marks: tuple[bool, bool], mocked: bool
) -> None:
    for name, mark in zip(("incremental", "legacy"), marks, strict=True):
        metadata = {"collector": name} | ({"mock": True} if mark else {})
        (tmp_path / f"{name}.json").write_text(json.dumps(metadata), newline="")

    assert mock(tmp_path) is mocked


def test_running_totals_that_fall_are_an_error(tmp_path: Path) -> None:
    csv = write(
        tmp_path / "trace.csv",
        "json_loads,7,0,100,0,1,2,250,40",
        "json_loads,7,0,200,0,1,3,240,40",
    )

    with pytest.raises(ValueError, match="json_loads worker 7's generation 0 totals"):
        load(csv)


def test_yield_is_collected_over_candidates() -> None:
    assert Tally(collections=4, candidates=200, collected=50).yield_ == 0.25


def test_yield_is_none_until_a_collection_had_a_candidate() -> None:
    assert Tally(collections=4).yield_ is None


def test_per_worker_is_a_generation_and_kinds_collections_over_the_workers() -> None:
    benchmark = Benchmark(4, {(2, "explicit"): Tally(10, 0, 0)})

    assert benchmark.per_worker(2, "explicit") == 2.5
    assert benchmark.per_worker(0, "automatic") == 0


def test_the_data_holds_the_five_benchmarks_under_both_collectors() -> None:
    data = load_data()

    assert {collector: set(benchmarks) for collector, benchmarks in data.items()} == {
        "incremental": FIVE,
        "legacy": FIVE,
    }
    for benchmarks in data.values():
        for benchmark in benchmarks.values():
            assert benchmark.workers > 0
            assert (0, "automatic") in benchmark.tallies
