import pytest

from pep848_sim.collectors.collector import Collector, CollectorSettings, Record
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.presets import CREATE_GC_CYCLES, PRESETS, Preset
from pep848_sim.run import run
from test_run import digest, records


def preset_records(preset: Preset, collector: type[Collector]) -> list[Record]:
    """A preset's records under a collector, at the PEP's default settings."""
    settings = CollectorSettings()
    return records(run(preset.workload, collector, settings, preset.run_length, 50))


def test_each_preset_is_named_for_its_benchmark() -> None:
    assert {name: preset.benchmark for name, preset in PRESETS.items()} == {
        "create_gc_cycles": "create_gc_cycles"
    }


@pytest.mark.parametrize(
    ("name", "collector", "pinned"),
    [
        ("create_gc_cycles", IncrementalCollector, "056d431af7a2b8f8"),
        ("create_gc_cycles", LegacyCollector, "3facc140edae9c35"),
    ],
)
def test_each_presets_records_keep_their_digest(
    name: str, collector: type[Collector], pinned: str
) -> None:
    """Pinned under CPython, which ADR 0007 makes Pyodide's digest too."""
    assert digest(preset_records(PRESETS[name], collector)) == pinned


@pytest.mark.parametrize("collector", [IncrementalCollector, LegacyCollector])
def test_create_gc_cycles_runs_its_loops_between_start_up_and_shutdown(
    collector: type[Collector],
) -> None:
    preset = CREATE_GC_CYCLES
    rings = preset.workload.structures[-1]

    whole = preset_records(preset, collector)

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
