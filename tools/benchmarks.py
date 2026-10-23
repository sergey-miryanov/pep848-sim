"""The benchmarks' collections, from the CSV files gcmon extracts from its traces of
pyperformance's workers (#117). The tests read them; sim.zip never ships them.

A preset models a worker whole (ADR 0011), so every collection counts: start-up,
imports, the benchmark's loops, pyperf's bookkeeping and shutdown alike.
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, NamedTuple

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# One run of pyperformance under each, on the reference branch.
COLLECTORS = ("incremental", "legacy")

# A collection is explicit when its row's `auto_collect` is 0, whoever started it:
# the benchmark's `gc.collect()`, pyperf or the interpreter shutting down.
type Kind = Literal["automatic", "explicit"]


class Tally(NamedTuple):
    """The runtime's counters for collections of one generation and kind: a
    worker's running totals as a row reads them, or what its collections added."""

    collections: int = 0
    candidates: int = 0
    collected: int = 0

    @property
    def yield_(self) -> float | None:
        """Collected over candidates, which a preset's yield is held to. None until
        a collection had a candidate."""
        return self.collected / self.candidates if self.candidates else None

    def add(self, other: Tally) -> Tally:
        return Tally(
            self.collections + other.collections,
            self.candidates + other.candidates,
            self.collected + other.collected,
        )

    def since(self, earlier: Tally) -> Tally:
        """What running totals gained since `earlier` read them."""
        return Tally(
            self.collections - earlier.collections,
            self.candidates - earlier.candidates,
            self.collected - earlier.collected,
        )


class Benchmark(NamedTuple):
    """One benchmark's collections under one collector, summed over its workers."""

    workers: int
    tallies: dict[tuple[int, Kind], Tally]
    # Real objects in the heap as each worker's first collection read began,
    # averaged over the workers whose rows report it.
    first_heap: float | None = None

    def per_worker(self, generation: int, kind: Kind) -> float:
        """How many collections of a generation and kind a worker makes: for
        explicit ones, how often its `gc.collect()` calls come."""
        return self.tallies.get((generation, kind), Tally()).collections / self.workers


def load(path: Path) -> dict[str, Benchmark]:
    """Each benchmark in one CSV file, by pyperformance's name for it, with
    pyperf's calibration workers left out."""
    workers: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row["calibration"] == "0":
                workers[row["benchmark"], row["worker"]].append(row)

    counts: Counter[str] = Counter()
    tallies: defaultdict[str, dict[tuple[int, Kind], Tally]] = defaultdict(dict)
    first_heaps: defaultdict[str, list[int]] = defaultdict(list)
    for (benchmark, worker), rows in workers.items():
        counts[benchmark] += 1
        rows.sort(key=lambda row: int(row["ts"]))
        # heap_size is a column the loader can do without.
        if first_heap := rows[0].get("heap_size"):
            first_heaps[benchmark].append(int(first_heap))
        # The runtime keeps running totals per worker and generation. A row
        # counts what they gained since the last row read them, so a record gcmon
        # lost folds into the next one it read. A record lost after a worker's
        # last row has nothing to fold into, and no total counts it.
        read: dict[int, Tally] = {}
        for row in rows:
            generation = int(row["generation"])
            totals = Tally(
                int(row["collections"]), int(row["candidates"]), int(row["collected"])
            )
            gained = totals.since(read.get(generation, Tally()))
            if min(gained) < 0:
                raise ValueError(
                    f"{benchmark} worker {worker}'s generation {generation} totals"
                    f" fall at ts {row['ts']}"
                )
            read[generation] = totals
            kind: Kind = "automatic" if row["auto_collect"] == "1" else "explicit"
            key = (generation, kind)
            tallies[benchmark][key] = tallies[benchmark].get(key, Tally()).add(gained)

    return {
        name: Benchmark(counts[name], tallies[name], _mean(first_heaps[name]))
        for name in sorted(counts)
    }


def _mean(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None


def load_data(directory: Path = DATA) -> dict[str, dict[str, Benchmark]]:
    """Each collector's benchmarks, from the files the rerun left in data/."""
    return {name: load(directory / f"{name}.csv") for name in COLLECTORS}


def mock(directory: Path = DATA) -> bool:
    """Whether the metadata beside any collector's file says its records are
    mock, as tools/mock_data.py writes them until the rerun."""
    return any(
        json.loads((directory / f"{name}.json").read_text(encoding="utf-8")).get(
            "mock", False
        )
        for name in COLLECTORS
    )
