from itertools import pairwise

import pytest

from benchmarks import Tally, load_data, mock
from compare_presets import COLLECTORS, run_preset, tally
from pep848_sim.collectors.collector import Collector, CollectorSettings
from pep848_sim.collectors.heap import Heap
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.presets import (
    ASYNC_TREE_IO_TG,
    CREATE_GC_CYCLES,
    JSON_LOADS,
    PRESETS,
    XML_ETREE_PARSE,
)
from pep848_sim.workload import Workload
from test_run import digest

# Placeholder until the rerun's records settle it (#117): how far a preset's yield
# may sit from its benchmark's, as a share of the objects examined.
YIELD_TOLERANCE = 0.05


def test_each_preset_is_named_for_its_benchmark() -> None:
    assert {name: preset.benchmark for name, preset in PRESETS.items()} == {
        "create_gc_cycles": "create_gc_cycles",
        "json_loads": "json_loads",
        "xml_etree_parse": "xml_etree_parse",
        "async_tree_io_tg": "async_tree_io_tg",
    }


@pytest.mark.parametrize(
    ("name", "collector", "pinned"),
    [
        ("create_gc_cycles", IncrementalCollector, "056d431af7a2b8f8"),
        ("create_gc_cycles", LegacyCollector, "3facc140edae9c35"),
        ("json_loads", IncrementalCollector, "6fafb92dad242ff4"),
        ("json_loads", LegacyCollector, "0b0de830268571c1"),
        ("xml_etree_parse", IncrementalCollector, "52482d165ce1db17"),
        ("xml_etree_parse", LegacyCollector, "19f765838ff779b7"),
        ("async_tree_io_tg", IncrementalCollector, "bf999cc59d2cdeec"),
        ("async_tree_io_tg", LegacyCollector, "229fe4e864440024"),
    ],
)
def test_each_presets_records_keep_their_digest(
    name: str, collector: type[Collector], pinned: str
) -> None:
    """Pinned under CPython, which ADR 0007 makes Pyodide's digest too."""
    assert digest(run_preset(PRESETS[name], collector)) == pinned


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_create_gc_cycles_runs_its_loops_between_start_up_and_shutdown(
    collector: type[Collector],
) -> None:
    preset = CREATE_GC_CYCLES
    rings = preset.workload.structures[-1]

    whole = run_preset(preset, collector)

    kinds = [record.kind for record in whole]
    first_loop = kinds.index("full")
    loops, shutdown = whole[first_loop:-2], whole[-2:]
    # gc.collect() comes too often for the runtime to start a collection once the
    # loops begin, and the last loop's second call ends the run.
    assert {record.kind for record in loops} == {"full"}
    assert len(loops) % 2 == 0
    assert loops[-1].clock == preset.run_length
    # Each loop's second gc.collect() frees the rings it dropped.
    rings_garbage = rings.shape.cyclic_garbage(rings.size)
    assert all(record.freed >= rings_garbage for record in loops[1::2])
    # Shutdown's first full collection leaves no cyclic garbage for the second.
    assert [record.kind for record in shutdown] == ["shutdown", "shutdown"]
    first, second = shutdown
    assert sum(first.spaces_after) == first.reachable_after
    assert second.freed == 0


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_json_loads_finds_no_cyclic_garbage_before_shutdown(
    collector: type[Collector],
) -> None:
    preset = JSON_LOADS
    tree = preset.workload.structures[1]

    *automatic, first, second = run_preset(preset, collector)

    # Nothing calls gc.collect(), so the runtime starts every collection before
    # shutdown, one each threshold0 kB, and no result json.loads returns leaves a
    # cycle for one to free.
    assert len(automatic) == preset.run_length // CollectorSettings().threshold0
    assert {record.kind for record in automatic}.isdisjoint({"full", "shutdown"})
    assert all(record.freed == 0 for record in automatic)
    # Shutdown's first full collection frees the start-up tree, and leaves the
    # second nothing.
    assert [first.kind, second.kind] == ["shutdown", "shutdown"]
    assert first.freed == tree.shape.cyclic_garbage(tree.size)
    assert second.freed == 0


def test_xml_etree_parse_builds_a_tree_then_parses_60_in_each_value() -> None:
    preset = XML_ETREE_PARSE
    workload = Workload(Heap(LegacyCollector()), preset.workload)

    workload.run_to(preset.run_length)

    # Start-up's two structures, then each of the four values: its own tree, the
    # third structure, and 60 parses of it, the fourth.
    built = [i for i, _, _ in workload.builds]
    assert built == [0, 1, *[2, *[3] * 60] * 4]
    # Each value ends as the next begins, and the last as the run does.
    value = preset.workload.structures[2].rebuild_interval
    assert value is not None
    starts = [first for i, first, _ in workload.builds if i == 2]
    assert [b - a for a, b in pairwise(starts)] == [value] * 3
    assert starts[-1] - 1 + value == preset.run_length


def test_async_tree_io_tg_drops_each_runs_tree_as_the_next_run_starts() -> None:
    preset = ASYNC_TREE_IO_TG
    tree = preset.workload.structures[2]
    assert tree.lifetime is not None
    workload = Workload(Heap(LegacyCollector()), preset.workload)

    workload.run_to(preset.run_length)

    # Start-up's two structures, then the tree once a run, four times.
    assert [i for i, _, _ in workload.builds] == [0, 1, *[2] * 4]
    # Each run's tree goes as the next run starts, and the last as the worker ends.
    trees = [(first, last) for i, first, last in workload.builds if i == 2]
    drops = [last + tree.lifetime for _, last in trees]
    assert drops == [*(first - 1 for first, _ in trees[1:]), preset.run_length]


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_async_tree_io_tg_finds_no_cyclic_garbage_before_shutdown(
    collector: type[Collector],
) -> None:
    *automatic, first, second = run_preset(ASYNC_TREE_IO_TG, collector)

    # Refcounting frees each tree, and nothing calls gc.collect().
    assert {record.kind for record in automatic}.isdisjoint({"full", "shutdown"})
    assert all(record.freed == 0 for record in automatic)
    assert [first.kind, second.kind] == ["shutdown", "shutdown"]


@pytest.mark.skipif(mock(), reason="the records in data/ are mock until the rerun")
@pytest.mark.parametrize("collector", COLLECTORS)
@pytest.mark.parametrize("name", PRESETS)
def test_each_presets_yields_match_its_benchmarks(name: str, collector: str) -> None:
    """By generation and kind, wherever the benchmark's collections examined an
    object (#117)."""
    preset = PRESETS[name]
    benchmark = load_data()[collector][preset.benchmark]

    simulated = tally(run_preset(preset, COLLECTORS[collector]))

    for key, target in sorted(benchmark.tallies.items()):
        if target.yield_ is not None:
            got = simulated.tallies.get(key, Tally()).yield_
            assert got == pytest.approx(target.yield_, abs=YIELD_TOLERANCE), key
