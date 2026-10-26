"""Run each preset under both collectors and print what its collections did beside
its benchmark's, as #117 loads them: by generation and kind, the collections a
worker makes and their yield, and the objects its first collection examines. We
change a preset's open parameters until the two agree (ADR 0011).
"""

from collections.abc import Iterable

from benchmarks import Benchmark, Kind, Tally, load_data
from pep848_sim.collectors.collector import Collector, CollectorSettings, Record
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.presets import PRESETS, Preset
from pep848_sim.run import run

# Each collector under the name its records in data/ go by.
COLLECTORS: dict[str, type[Collector]] = {
    "incremental": IncrementalCollector,
    "legacy": LegacyCollector,
}

# Where the runtime's stats file each kind of record: its generation, and whether
# the runtime started the collection on its own. Shutdown's set no target (#117),
# so they file nowhere.
FILED: dict[str, tuple[int, Kind] | None] = {
    "young": (0, "automatic"),
    "old": (1, "automatic"),
    "gen 0": (0, "automatic"),
    "gen 1": (1, "automatic"),
    "gen 2": (2, "automatic"),
    "full": (2, "explicit"),
    "shutdown": None,
}

# Real objects to a simulated one (ADR 0002).
REAL_PER_SIMULATED = 16


def run_preset(preset: Preset, collector: type[Collector]) -> list[Record]:
    """A preset's records under a collector, at the PEP's default settings."""
    parts = run(preset.workload, collector, CollectorSettings(), preset.run_length, 1)
    return [record for part in parts for record in part]


def tally(records: Iterable[Record]) -> Benchmark:
    """A run's records as one worker's collections, tallied as #117 tallies a
    benchmark's: the objects a collection examined are its candidates, and those
    it freed are what it collected."""
    tallies: dict[tuple[int, Kind], Tally] = {}
    first_examined = None
    for record in records:
        examined = record.survived + record.freed
        if first_examined is None:
            first_examined = examined * REAL_PER_SIMULATED
        key = FILED[record.kind]
        if key is None:
            continue
        collection = Tally(1, examined, record.freed)
        tallies[key] = tallies.get(key, Tally()).add(collection)
    return Benchmark(1, tallies, first_examined)


def report(title: str, benchmark: Benchmark, preset: Benchmark) -> list[str]:
    """The lines that set a preset's collections beside its benchmark's."""
    lines = [
        title,
        f"  {'':<14}{'per worker':^20}  {'yield':^20}",
        f"  {'':<14}{'benchmark':>10}{'preset':>10}  {'benchmark':>10}{'preset':>10}",
    ]
    for generation, kind in sorted(benchmark.tallies.keys() | preset.tallies.keys()):
        lines.append(
            f"  gen {generation} {kind:<9}"
            f"{benchmark.per_worker(generation, kind):>10.1f}"
            f"{preset.per_worker(generation, kind):>10.1f}  "
            f"{_share(benchmark, generation, kind):>10}"
            f"{_share(preset, generation, kind):>10}"
        )
    lines.append(
        "  the first collection examines, in real objects:"
        f" benchmark {_count(benchmark.first_examined)},"
        f" preset {_count(preset.first_examined)}"
    )
    return lines


def _share(benchmark: Benchmark, generation: int, kind: Kind) -> str:
    share = benchmark.tallies.get((generation, kind), Tally()).yield_
    return "-" if share is None else f"{share:.1%}"


def _count(objects: float | None) -> str:
    return "-" if objects is None else f"{objects:,.0f}"


def main() -> None:
    data = load_data()
    for name, preset in PRESETS.items():
        for collector, make in COLLECTORS.items():
            title = f"{name} under the {collector} collector"
            simulated = tally(run_preset(preset, make))
            print(
                "\n".join(report(title, data[collector][preset.benchmark], simulated))
            )
            print()


if __name__ == "__main__":
    main()
