import json
from itertools import pairwise

import pytest

from benchmarks import Tally
from compare_presets import COLLECTORS, benchmark, run_preset, tally
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
    Preset,
)
from pep848_sim.widget.request import runs
from pep848_sim.workload import Workload
from test_run import PINNED, digest, records

# How far a preset's yield may sit from its benchmark's: a fifth of the
# benchmark's, or half a point of the objects examined, whichever is wider. A
# benchmark's workers agree to within 0.01 points, so the width goes to the
# preset's coarser model (#117). Half a point keeps a preset that finds no
# cyclic garbage apart from a benchmark whose collections find 1%.
YIELD_REL, YIELD_ABS = 0.2, 0.005


def start_up_garbage(preset: Preset) -> int:
    """The cyclic garbage of the two trees start-up lets go of, its first
    structure and its fourth."""
    structures = preset.workload.structures
    return sum(s.shape.cyclic_garbage(s.size) for s in (structures[0], structures[3]))


def start_up_trees(preset: Preset) -> int:
    """The cyclic garbage of the two trees under the module root, which start-up
    builds before its first collection and after it: its third structure and its
    fifth."""
    structures = preset.workload.structures
    return sum(s.shape.cyclic_garbage(s.size) for s in (structures[2], structures[4]))


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
    rings = preset.workload.structures[6]

    whole = run_preset(preset, collector)

    kinds = [record.kind for record in whole]
    first_loop = kinds.index("full")
    loops, shutdown = whole[first_loop:-3], whole[-3:]
    # The loops begin once the structures that build once have built.
    once = [s for s in preset.workload.structures if s.rebuild_interval is None]
    assert loops[0].clock == sum(s.build_length for s in once)
    # gc.collect() comes too often for the runtime to start a collection once the
    # loops begin, and the last loop's second call ends the run.
    assert {record.kind for record in loops} == {"full"}
    assert len(loops) % 2 == 0
    assert loops[-1].clock == preset.run_length
    # Each loop's second gc.collect() frees the rings it dropped.
    rings_garbage = rings.shape.cyclic_garbage(rings.size)
    assert all(record.freed >= rings_garbage for record in loops[1::2])
    # The last loop freed its rings, so shutdown's first full collection finds no
    # cyclic garbage the frames left. The second frees the start-up trees once the
    # modules go, and leaves the third none.
    assert [record.kind for record in shutdown] == ["shutdown"] * 3
    first, second, third = shutdown
    assert first.freed == 0
    assert second.freed == start_up_trees(preset)
    assert sum(second.spaces_after) == second.reachable_after
    assert third.freed == 0


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_json_loads_loops_leave_no_cyclic_garbage(
    collector: type[Collector],
) -> None:
    preset = JSON_LOADS

    *automatic, first, second, third = run_preset(preset, collector)

    # Nothing calls gc.collect(), so the runtime starts every collection before
    # shutdown, one each threshold0 kB. No result json.loads returns leaves a
    # cycle, so they and shutdown's first full collection free the trees start-up
    # let go of and nothing more.
    assert len(automatic) == preset.run_length // CollectorSettings().threshold0
    assert {record.kind for record in automatic}.isdisjoint({"full", "shutdown"})
    assert [first.kind, second.kind, third.kind] == ["shutdown"] * 3
    freed = sum(record.freed for record in automatic) + first.freed
    assert freed == start_up_garbage(preset)
    # The second frees the start-up trees under sys once the modules go, and
    # leaves the third nothing.
    assert second.freed == start_up_trees(preset)
    assert third.freed == 0


def test_xml_etree_parse_builds_a_tree_then_parses_60_in_each_value() -> None:
    preset = XML_ETREE_PARSE
    workload = Workload(Heap(LegacyCollector()), preset.workload)

    workload.run_to(preset.run_length)

    # Start-up's six structures, the cycles xml.etree lets go of and what pyperf
    # allocates, the eleventh and the twelfth, then each of the four values: its
    # own tree, the seventh structure, its serialising, the eighth, 60 parses of
    # the tree, the ninth, and the serialising of the last two parsed trees, the
    # tenth. A fifth value's tree builds as the run ends.
    built = [i for i, _, _ in workload.builds]
    assert built == [0, 1, 2, 3, 4, 5, 10, 11, *[6, 7, *[8] * 60, 9] * 4, 6]
    # Each value ends as the next begins, and the run ends while the fifth one
    # serialises its tree.
    tree, serialising = preset.workload.structures[6:8]
    assert tree.rebuild_interval is not None
    starts = [first for i, first, _ in workload.builds if i == 6]
    assert [b - a for a, b in pairwise(starts)] == [tree.rebuild_interval] * 4
    python = tree.build_length + serialising.build_length
    assert starts[-1] + tree.build_length <= preset.run_length < starts[-1] + python


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_xml_etree_parse_collects_as_a_parse_ends_if_one_is_under_way(
    collector: type[Collector],
) -> None:
    """C code parses each tree, and holds back a collection until it returns."""
    preset = XML_ETREE_PARSE
    collecting = collector(CollectorSettings())
    workload = Workload(Heap(collecting), preset.workload)
    workload.run_to(preset.run_length)
    parses = {last for i, _, last in workload.builds if i == 8}
    clocks = [0, *(r.clock for r in collecting.records)]

    gaps = [(b - a, b in parses) for a, b in pairwise(clocks)]

    # Each collection comes threshold0 kB after the last, or later as a parse ends.
    # Each worker whose 51 gcmon read starts 40 more than 5 kB late.
    threshold0 = CollectorSettings().threshold0
    assert all(gap == threshold0 or (gap > threshold0 and ends) for gap, ends in gaps)
    assert sum(gap > threshold0 for gap, _ in gaps) == 40


def test_xml_etree_parse_gen_0_collections_find_three_parsed_trees_as_it_parses() -> (
    None
):
    """Under the legacy collector, a gen 0 collection a parse holds back finds the
    tree it parsed and the two before it young, and one in a value's Python finds
    the value's own tree at most, with start-up's last at the first."""
    preset = XML_ETREE_PARSE
    parsed = preset.workload.structures[8].size
    records = run_preset(preset, LegacyCollector)
    starts = [0, *(r.clock for r in records)]
    threshold0 = CollectorSettings().threshold0

    gen_0 = [
        (r.survived + r.freed, r.clock - last > threshold0)
        for r, last in zip(records, starts, strict=False)
        if r.kind == "gen 0"
    ]

    late = [examined for examined, held in gen_0 if held]
    on_time = [examined for examined, held in gen_0[2:] if not held]
    assert len(late) == 36
    assert all(3 * parsed <= examined < 4 * parsed for examined in late)
    assert all(examined < 2 * parsed for examined in on_time)


def test_async_tree_io_tg_drops_each_runs_tree_before_the_next_run_starts() -> None:
    preset = ASYNC_TREE_IO_TG
    tree, finished = preset.workload.structures[6:8]
    assert tree.lifetime is not None
    assert finished.lifetime is not None
    workload = Workload(Heap(LegacyCollector()), preset.workload)

    workload.run_to(preset.run_length)

    # Start-up's six structures and the set-up, then the tree and what its tasks
    # keep as they finish, once a run, four times.
    assert [i for i, _, _ in workload.builds] == [0, 1, 2, 3, 4, 5, 8, *[6, 7] * 4]
    trees = [(first, last) for i, first, last in workload.builds if i == 6]
    finishes = [(first, last) for i, first, last in workload.builds if i == 7]
    # Each run's tree goes while its tasks finish, and what they keep goes 2 MB
    # before the next run starts, the last 2 MB before the worker ends.
    for (_, built), (first, last) in zip(trees, finishes, strict=True):
        assert built + 1 == first
        assert first < built + tree.lifetime < last
    ends = [last + finished.lifetime + 2_000 for _, last in finishes]
    assert ends == [*(first - 1 for first, _ in trees[1:]), preset.run_length]


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_async_tree_io_tg_runs_leave_no_cyclic_garbage(
    collector: type[Collector],
) -> None:
    *automatic, first, second, third = run_preset(ASYNC_TREE_IO_TG, collector)

    # Refcounting frees each tree, and nothing calls gc.collect(), so the
    # collections before shutdown and shutdown's first free the trees start-up let
    # go of and nothing more.
    assert {record.kind for record in automatic}.isdisjoint({"full", "shutdown"})
    assert [first.kind, second.kind, third.kind] == ["shutdown"] * 3
    freed = sum(record.freed for record in automatic) + first.freed
    assert freed == start_up_garbage(ASYNC_TREE_IO_TG)


def test_connected_components_takes_node_then_adj_then_its_reader() -> None:
    """The branch's first young collection of the graph leaves G._node, which
    G.__dict__ took over from G, behind the nodes and edges it keeps in place, so
    the sweep reaches _node first. Its increment at 48 MB takes the attribute
    dicts so far, young ones too (ADR 0024). _adj's at 60 MB takes the adjacency
    dicts and edges, but not the attribute dicts made since, which the young
    collections after it find. read_adjlist's reader, older than the graph, waits
    pending until the budget pays the increment back (ADR 0025)."""
    records = run_preset(CONNECTED_COMPONENTS, IncrementalCollector)

    def work(r: Record) -> int:
        return r.marked + r.survived + r.freed

    first = [r for r in records if r.kind == "old" and r.sweep == 1]
    largest = sorted(sorted(first, key=work)[-2:], key=lambda r: r.clock)
    assert [r.clock for r in largest] == [48_000, 60_000]
    young = [r for r in records if r.kind == "young" and 60_000 < r.clock < 80_000]
    full = max(work(r) for r in records if r.kind == "young")
    assert all(0 < work(r) < full / 3 for r in young)
    ended = next(r for r in records if r.sweep == 2)
    # The reader, and G, its __dict__ and the cache, which _adj's increment left.
    reader = CONNECTED_COMPONENTS.workload.structures[8]
    assert (ended.clock, work(ended)) == (96_000, reader.size + 3)


def wrappers() -> list[int]:
    """The cyclic garbage networkx's wrappers leave as the load starts and as the
    walks start, connected_components' eighth structure and its eleventh."""
    structures = CONNECTED_COMPONENTS.workload.structures
    return [s.shape.cyclic_garbage(s.size) for s in (structures[7], structures[10])]


def test_connected_components_young_collections_free_the_wrappers_cycles() -> None:
    """As its workers' do: start-up's trees at 22 and 26 MB, read_adjlist's and
    empty_graph's wrappers at 38 MB and connected_components' at 146 MB."""
    records = run_preset(CONNECTED_COMPONENTS, IncrementalCollector)
    freed = [(r.clock, r.freed) for r in records if r.kind == "young" and r.freed]
    load, walk = wrappers()
    assert freed[2:] == [(38_000, load), (146_000, walk)]
    assert sum(f for _, f in freed[:2]) == start_up_garbage(CONNECTED_COMPONENTS)


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_connected_components_frees_its_graph_as_its_frames_return(
    collector: type[Collector],
) -> None:
    *automatic, first, second, third = run_preset(CONNECTED_COMPONENTS, collector)

    # The walks make no cycles, and read_adjlist's frame holds the graph, so the
    # collections before shutdown free the trees start-up let go of and the cycles
    # networkx's wrappers leave, and nothing more. Nothing in the graph links
    # back, so refcounting frees it once the worker's frames have returned, and
    # shutdown's first full collection finds none of it. The second frees
    # start-up's trees, which their cycles keep once the modules go, and leaves
    # the third nothing.
    assert [first.kind, second.kind, third.kind] == ["shutdown"] * 3
    freed = sum(record.freed for record in automatic)
    assert freed == start_up_garbage(CONNECTED_COMPONENTS) + sum(wrappers())
    assert first.freed == 0
    assert second.freed == start_up_trees(CONNECTED_COMPONENTS)
    assert third.freed == 0


@pytest.mark.parametrize(
    ("name", "collector"),
    [(name, collector) for name in PRESETS for collector in COLLECTORS],
)
def test_each_presets_yields_match_its_benchmarks(name: str, collector: str) -> None:
    """By generation and kind, wherever the benchmark's collections examined an
    object (#117), within the kB the preset's run allocates."""
    preset = PRESETS[name]
    target_benchmark = benchmark(preset, collector)

    simulated = tally(run_preset(preset, COLLECTORS[collector]))

    for key, target in sorted(target_benchmark.tallies.items()):
        if target.yield_ is not None:
            got = simulated.tallies.get(key, Tally()).yield_
            wanted = pytest.approx(target.yield_, rel=YIELD_REL, abs=YIELD_ABS)
            assert got == wanted, key
