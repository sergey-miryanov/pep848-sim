import base64
import json
import re
import zlib
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from benchmarks import Tally, load_data
from compare_presets import COLLECTORS, run_preset, tally
from pep848_sim.collectors.collector import Collector, CollectorSettings, Record
from pep848_sim.collectors.heap import Heap
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.presets import (
    ASYNC_TREE_IO_TG,
    CONNECTED_COMPONENTS,
    CREATE_GC_CYCLES,
    JSON_LOADS,
    PRESETS,
    XML_ETREE_PARSE,
)
from pep848_sim.widget.request import expand, runs
from pep848_sim.workload import Workload
from test_run import PINNED, digest, records

ROOT = Path(__file__).parent.parent
# The requests the guide's widgets send for async_tree_io_tg and, in the section
# on uncollected garbage, for json_loads.
GUIDES_ASYNC_TREE_IO_TG = json.dumps(
    {
        "preset": "async_tree_io_tg",
        "settings": {"threshold0": 2000, "threshold1": 10, "threshold2": 10},
        "every": 10,
    }
)
GUIDES_JSON_LOADS = json.dumps(
    {
        "preset": "json_loads",
        "settings": {"threshold0": 2000, "threshold1": 10, "threshold2": 10},
        "every": 1,
    }
)

# How far a preset's yield may sit from its benchmark's: a fifth of the
# benchmark's, or half a point of the objects examined, whichever is wider. A
# benchmark's workers agree to within 0.01 points, so the width goes to the
# preset's coarser model (#117). Half a point keeps a preset that finds no
# cyclic garbage apart from a benchmark whose collections find 1%.
YIELD_REL, YIELD_ABS = 0.2, 0.005


def test_each_preset_is_named_for_its_benchmark() -> None:
    assert {name: preset.benchmark for name, preset in PRESETS.items()} == {
        "create_gc_cycles": "create_gc_cycles",
        "json_loads": "json_loads",
        "xml_etree_parse": "xml_etree_parse",
        "async_tree_io_tg": "async_tree_io_tg",
        "connected_components": "connected_components",
    }


def test_each_preset_has_its_digests_pinned_for_a_request_at_the_peps_settings() -> (
    None
):
    assert {
        name: pinned["request"] for name, pinned in PINNED.items() if name != "fixed"
    } == {
        name: {
            "preset": name,
            "settings": {"threshold0": 2000, "threshold1": 10, "threshold2": 10},
            "every": 5,
        }
        for name in PRESETS
    }


@pytest.mark.parametrize("name", list(PRESETS))
def test_each_presets_records_keep_their_digest(name: str) -> None:
    """Through the worker's path, as tests/digests.pyodide.js runs them."""
    legacy, incremental = runs(json.dumps(PINNED[name]["request"]))

    assert digest(records(legacy)) == PINNED[name]["legacy"]
    assert digest(records(incremental)) == PINNED[name]["incremental"]


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_a_presets_request_runs_as_the_preset_does(collector: type[Collector]) -> None:
    """The comparison script runs a preset as the worker does."""
    name = "json_loads"
    legacy, incremental = runs(json.dumps(PINNED[name]["request"]))
    parts = legacy if collector is LegacyCollector else incremental

    assert records(parts) == run_preset(PRESETS[name], collector)


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_create_gc_cycles_runs_its_loops_between_start_up_and_shutdown(
    collector: type[Collector],
) -> None:
    preset = CREATE_GC_CYCLES
    _, _, start_up_tree, _, rings = preset.workload.structures

    whole = run_preset(preset, collector)

    kinds = [record.kind for record in whole]
    first_loop = kinds.index("full")
    loops, shutdown = whole[first_loop:-3], whole[-3:]
    # gc.collect() comes too often for the runtime to start a collection once the
    # loops begin, and the last loop's second call ends the run.
    assert {record.kind for record in loops} == {"full"}
    assert len(loops) % 2 == 0
    assert loops[-1].clock == preset.run_length
    # Each loop's second gc.collect() frees the rings it dropped.
    rings_garbage = rings.shape.cyclic_garbage(rings.size)
    assert all(record.freed >= rings_garbage for record in loops[1::2])
    # The last loop freed its rings, so shutdown's first full collection finds no
    # cyclic garbage the frames left. The second frees the start-up tree once the
    # modules go, and leaves the third none.
    assert [record.kind for record in shutdown] == ["shutdown"] * 3
    first, second, third = shutdown
    assert first.freed == 0
    assert second.freed == start_up_tree.shape.cyclic_garbage(start_up_tree.size)
    assert sum(second.spaces_after) == second.reachable_after
    assert third.freed == 0


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_json_loads_loops_leave_no_cyclic_garbage(
    collector: type[Collector],
) -> None:
    preset = JSON_LOADS
    garbage, _, tree, _ = preset.workload.structures

    *automatic, first, second, third = run_preset(preset, collector)

    # Nothing calls gc.collect(), so the runtime starts every collection before
    # shutdown, one each threshold0 kB. No result json.loads returns leaves a
    # cycle, so they and shutdown's first full collection free the tree start-up
    # let go of and nothing more.
    assert len(automatic) == preset.run_length // CollectorSettings().threshold0
    assert {record.kind for record in automatic}.isdisjoint({"full", "shutdown"})
    assert [first.kind, second.kind, third.kind] == ["shutdown"] * 3
    freed = sum(record.freed for record in automatic) + first.freed
    assert freed == garbage.shape.cyclic_garbage(garbage.size)
    # The second frees the start-up tree under sys once the modules go, and leaves
    # the third nothing.
    assert second.freed == tree.shape.cyclic_garbage(tree.size)
    assert third.freed == 0


def test_xml_etree_parse_builds_a_tree_then_parses_60_in_each_value() -> None:
    preset = XML_ETREE_PARSE
    workload = Workload(Heap(LegacyCollector()), preset.workload)

    workload.run_to(preset.run_length)

    # Start-up's four structures, then each of the four values: its own tree, the
    # fifth structure, and 60 parses of it, the sixth.
    built = [i for i, _, _ in workload.builds]
    assert built == [0, 1, 2, 3, *[4, *[5] * 60] * 4]
    # Each value ends as the next begins, and the last as the run does.
    value = preset.workload.structures[4].rebuild_interval
    assert value is not None
    starts = [first for i, first, _ in workload.builds if i == 4]
    assert [b - a for a, b in pairwise(starts)] == [value] * 3
    assert starts[-1] - 1 + value == preset.run_length


def test_async_tree_io_tg_drops_each_runs_tree_as_the_next_run_starts() -> None:
    preset = ASYNC_TREE_IO_TG
    tree = preset.workload.structures[4]
    assert tree.lifetime is not None
    workload = Workload(Heap(LegacyCollector()), preset.workload)

    workload.run_to(preset.run_length)

    # Start-up's four structures, then the tree once a run, four times.
    assert [i for i, _, _ in workload.builds] == [0, 1, 2, 3, *[4] * 4]
    # Each run's tree goes as the next run starts, and the last as the worker ends.
    trees = [(first, last) for i, first, last in workload.builds if i == 4]
    drops = [last + tree.lifetime for _, last in trees]
    assert drops == [*(first - 1 for first, _ in trees[1:]), preset.run_length]


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_async_tree_io_tg_runs_leave_no_cyclic_garbage(
    collector: type[Collector],
) -> None:
    garbage = ASYNC_TREE_IO_TG.workload.structures[0]

    *automatic, first, second, third = run_preset(ASYNC_TREE_IO_TG, collector)

    # Refcounting frees each tree, and nothing calls gc.collect(), so the
    # collections before shutdown and shutdown's first free the tree start-up let
    # go of and nothing more.
    assert {record.kind for record in automatic}.isdisjoint({"full", "shutdown"})
    assert [first.kind, second.kind, third.kind] == ["shutdown"] * 3
    freed = sum(record.freed for record in automatic) + first.freed
    assert freed == garbage.shape.cyclic_garbage(garbage.size)


def test_async_tree_io_tg_runs_alike_whatever_the_freed_credit() -> None:
    """Its old collections free nothing, as no benchmark's did on the reference
    branch, so the freed-credit multiplier changes no record (the guide's section
    on the work budget)."""
    spelled = json.loads(expand(GUIDES_ASYNC_TREE_IO_TG))

    def incremental(freed_credit: int) -> list[Record]:
        spelled["constants"]["freed_credit"] = freed_credit
        _, run = runs(json.dumps(spelled))
        return [record for part in run for record in part]

    assert incremental(0) == incremental(10)


def guides_link(section: str) -> Any:
    """The request of the one link to the playground's async_tree_io_tg in the
    guide's section of that id, as the playground writes a link (site/link.js):
    deflate-raw JSON in base64url."""
    guide = (ROOT / "site" / "guide-long.html").read_text(encoding="utf-8")
    [body] = re.findall(rf'<section id="{section}">(.*?)</section>', guide, re.DOTALL)
    [text] = re.findall(
        r"playground=async_tree_io_tg&amp;playground\.request=([\w-]+)", body
    )
    padded = text + "=" * (-len(text) % 4)
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(padded), -15))


def test_the_guides_link_opens_async_tree_io_tg_with_parent_pointers() -> None:
    """The section on the work budget links to the preset's workload with its task
    tree given parent pointers."""
    wanted = json.loads(expand(GUIDES_ASYNC_TREE_IO_TG))
    tree = wanted["workload"]["structures"][4]
    assert tree["shape"] == {"hierarchy": 6}
    tree["shape"] = "tree"
    assert guides_link("the-work-budget") == wanted


def test_json_loads_cycles_wait_for_shutdown_under_the_incremental_collector() -> None:
    """Its run ends before its young generation fills, so the incremental collector
    examines nothing before shutdown, where the legacy collector's gen 0
    collections free cycles as they come loose (the guide's section on
    uncollected garbage)."""
    spelled = json.loads(expand(GUIDES_JSON_LOADS))
    spelled["workload"]["churn"]["cycle_share"] = "1/10"
    legacy, incremental = (
        [record for part in run for record in part] for run in runs(json.dumps(spelled))
    )

    garbage = JSON_LOADS.workload.structures[0]
    start_up = garbage.shape.cyclic_garbage(garbage.size)
    assert all(
        record.marked + record.survived + record.freed == 0
        for record in incremental
        if record.kind != "shutdown"
    )
    assert sum(r.freed for r in legacy if r.kind != "shutdown") > 10 * start_up


def test_the_guides_link_opens_async_tree_io_tg_with_long_lived_cycles() -> None:
    """The section on uncollected garbage links to the preset's workload with a
    tenth of its churn starting cycles, and its churn living 10 MB on average."""
    wanted = json.loads(expand(GUIDES_ASYNC_TREE_IO_TG))
    churn = wanted["workload"]["churn"]
    assert (churn["cycle_share"], churn["lifetime_mean"]) == ("0", 4)
    churn.update(cycle_share="1/10", lifetime_mean=10_000)
    assert guides_link("uncollected-garbage-and-peak-memory") == wanted


def test_connected_components_examines_its_graph_in_increments_while_it_loads() -> None:
    """read_adjlist's frame holds the graph until it returns, so sys reaches none
    of it while it loads, and an old collection's increment takes it: more than a
    young collection's survivors, all the work budget gains from one, could pay
    for."""
    records = run_preset(CONNECTED_COMPONENTS, IncrementalCollector)

    examined = [r.survived + r.freed for r in records if r.kind == "old"]

    assert max(examined) > CollectorSettings().threshold0


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_connected_components_frees_its_graph_with_its_module_at_shutdown(
    collector: type[Collector],
) -> None:
    garbage, _, start_up_tree, _, graph = CONNECTED_COMPONENTS.workload.structures

    *automatic, first, second, third = run_preset(CONNECTED_COMPONENTS, collector)

    # The walks make no cycles, and the graph stays in its module's globals, so
    # the collections before shutdown and shutdown's first free the tree start-up
    # let go of and nothing more. Shutdown's first full collection comes while the
    # modules still hold the graph and the start-up tree. The second frees both,
    # which their cycles keep once the modules go, and leaves the third nothing.
    assert [first.kind, second.kind, third.kind] == ["shutdown"] * 3
    freed = sum(record.freed for record in automatic) + first.freed
    assert freed == garbage.shape.cyclic_garbage(garbage.size)
    assert second.freed == graph.size + start_up_tree.size
    assert third.freed == 0


@pytest.mark.parametrize(
    ("name", "collector"),
    [(name, collector) for name in PRESETS for collector in COLLECTORS],
)
def test_each_presets_yields_match_its_benchmarks(name: str, collector: str) -> None:
    """By generation and kind, wherever the benchmark's collections examined an
    object (#117)."""
    preset = PRESETS[name]
    benchmark = load_data()[collector][preset.benchmark]

    simulated = tally(run_preset(preset, COLLECTORS[collector]))

    for key, target in sorted(benchmark.tallies.items()):
        if target.yield_ is not None:
            got = simulated.tallies.get(key, Tally()).yield_
            wanted = pytest.approx(target.yield_, rel=YIELD_REL, abs=YIELD_ABS)
            assert got == wanted, key
