"""Run each preset under both collectors and print what its collections did beside
its benchmark's, as #117 loads them: by generation and kind, the collections a
worker makes, the real objects one of them examines on average and their yield,
the objects its first collection examines, and the kB allocated as its last
collection before shutdown starts. A worker's collections that start past the
kB the preset's run allocates count for none of the rest: a run that ends sooner
cannot make them. We change a preset's open workload parameters until the two
agree (ADR 0011).
"""

from collections.abc import Iterable

from benchmarks import Benchmark, Kind, Tally, summed, workers_data
from pep848_sim.collectors.collector import (
    Collector,
    CollectorSettings,
    Constants,
    Record,
)
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

# A column's heads: the benchmark's figure, then the preset's.
_SIDES = f"{'benchmark':>10}{'preset':>10}"


def run_preset(preset: Preset, collector: type[Collector]) -> list[Record]:
    """A preset's records under a collector, at the PEP's default settings."""
    parts = run(preset.workload, collector, CollectorSettings(), preset.run_length, 1)
    return [record for part in parts for record in part]


def tally(records: Iterable[Record], constants: Constants | None = None) -> Benchmark:
    """A run's records as one worker's collections, tallied as #117 tallies a
    benchmark's, in real objects by the run's constants, the defaults unless
    given: the objects a collection examined are its candidates, and those it
    freed are what it collected. The clock reads kB allocated."""
    constants = constants or Constants()
    tallies: dict[tuple[int, Kind], Tally] = {}
    first_examined = None
    last_started = None
    for record in records:
        examined = constants.real(record.survived + record.freed)
        if first_examined is None:
            first_examined = examined
        key = FILED[record.kind]
        if key is None:
            continue
        last_started = record.clock
        collection = Tally(1, examined, constants.real(record.freed))
        tallies[key] = tallies.get(key, Tally()).add(collection)
    return Benchmark(1, tallies, first_examined, last_started)


def benchmark(preset: Preset, collector: str) -> Benchmark:
    """A preset's benchmark under a collector, its workers' collections summed
    within the kB the preset's run allocates."""
    workers = workers_data()[collector][preset.benchmark]
    return summed(workers, preset.run_length)


def report(title: str, benchmark: Benchmark, preset: Benchmark) -> list[str]:
    """The lines that set a preset's collections beside its benchmark's."""
    lines = [
        title,
        f"  {'':<14}{'per worker':^20}  {'examined each':^20}  {'yield':^20}",
        f"  {'':<14}{_SIDES}  {_SIDES}  {_SIDES}",
    ]
    for generation, kind in sorted(benchmark.tallies.keys() | preset.tallies.keys()):
        theirs = benchmark.tallies.get((generation, kind), Tally())
        ours = preset.tallies.get((generation, kind), Tally())
        lines.append(
            f"  gen {generation} {kind:<9}"
            f"{benchmark.per_worker(generation, kind):>10.1f}"
            f"{preset.per_worker(generation, kind):>10.1f}  "
            f"{_count(theirs.examined_each):>10}{_count(ours.examined_each):>10}  "
            f"{_share(theirs.yield_):>10}{_share(ours.yield_):>10}"
        )
    lines.append(
        "  the first collection examines, in real objects:"
        f" benchmark {_count(benchmark.first_examined)},"
        f" preset {_count(preset.first_examined)}"
    )
    lines.append(
        "  the last collection before shutdown starts, in kB allocated:"
        f" benchmark {_count(benchmark.last_started)},"
        f" preset {_count(preset.last_started)}"
    )
    return lines


def _share(share: float | None) -> str:
    return "-" if share is None else f"{share:.1%}"


def _count(objects: float | None) -> str:
    return "-" if objects is None else f"{objects:,.0f}"


def main() -> None:
    for name, preset in PRESETS.items():
        for collector, make in COLLECTORS.items():
            title = f"{name} under the {collector} collector"
            simulated = tally(run_preset(preset, make))
            print("\n".join(report(title, benchmark(preset, collector), simulated)))
            print()


if __name__ == "__main__":
    main()
