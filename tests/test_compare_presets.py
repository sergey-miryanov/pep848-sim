from benchmarks import Benchmark, Tally
from compare_presets import report, tally
from test_figures import record


def test_tally_files_each_record_where_the_runtimes_stats_would() -> None:
    records = [
        record(kind="young", survived=3, freed=1, spaces_before=(4, 2)),
        record(kind="old", marked=9, survived=5),
        record(kind="gen 2", survived=2, freed=2),
        record(kind="full", survived=6, freed=2),
        record(kind="shutdown", freed=4),
    ]

    # In real objects, 16 to a simulated one.
    assert tally(records) == Benchmark(
        workers=1,
        tallies={
            (0, "automatic"): Tally(1, 64, 16),
            # Marking examines nothing, so it adds no candidate.
            (1, "automatic"): Tally(1, 80, 0),
            (2, "automatic"): Tally(1, 64, 32),
            # Shutdown's sets no target, as #117 loads its benchmark's.
            (2, "explicit"): Tally(1, 128, 32),
        },
        # What the young collection examined.
        first_examined=64,
    )


def test_a_run_without_records_has_no_first_collection() -> None:
    assert tally([]) == Benchmark(1, {}, None)


def test_the_report_sets_each_generation_and_kind_beside_the_benchmarks() -> None:
    benchmark = Benchmark(
        workers=4,
        tallies={(0, "automatic"): Tally(8, 96, 0), (2, "explicit"): Tally(4, 80, 20)},
        first_examined=8_400,
    )
    preset = Benchmark(1, {(2, "explicit"): Tally(1, 10_000, 3_000)}, None)

    lines = report("json_loads under the legacy collector", benchmark, preset)

    assert lines[0] == "json_loads under the legacy collector"
    assert lines[1].split() == ["per", "worker", "examined", "each", "yield"]
    assert lines[3].split() == [
        *("gen", "0", "automatic"),
        *("2.0", "0.0"),
        *("12", "-"),
        *("0.0%", "-"),
    ]
    assert lines[4].split() == [
        *("gen", "2", "explicit"),
        *("1.0", "1.0"),
        *("20", "10,000"),
        *("25.0%", "30.0%"),
    ]
    assert lines[5] == (
        "  the first collection examines, in real objects: benchmark 8,400, preset -"
    )
