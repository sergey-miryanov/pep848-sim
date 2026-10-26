"""The benchmarks' collections, from the CSV files gcmon extracts from its traces of
pyperformance's workers (#117). The tests read them; sim.zip never ships them.

A preset models a worker whole (ADR 0011), so every collection before shutdown
counts: start-up, imports, the benchmark's loops and pyperf's bookkeeping alike.
Shutdown's collections set no target, since gcmon can lose them.
"""

import csv
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path
from typing import Literal, NamedTuple

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# One run of pyperformance under each collector, on the reference branch: the
# file gcmon extracted from its trace, with the trace's metadata beside it.
FILES = {"incremental": "pp-inc.csv", "legacy": "pp-legacy.csv"}

# A collection is explicit when its row's `auto_collect` is 0: the benchmark's
# `gc.collect()` calls, and shutdown's, which the loader leaves out.
type Kind = Literal["automatic", "explicit"]

# The branch's `_PyGC_Reason` for a collection gc.collect() asks for. Shutdown's
# first collection, `PyGC_Collect()` in `_Py_Finalize`, carries it too.
MANUAL = "2"
# The reason finalize_modules' two collections carry.
SHUTDOWN = "1"


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

    @property
    def examined_each(self) -> float | None:
        """The candidates of one collection on average: the objects it examined.
        None without a collection."""
        return self.candidates / self.collections if self.collections else None

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
    # Real objects each worker's first collection examined, which set start-up's
    # size (ADR 0011), averaged over the workers whose first collection gcmon read.
    first_examined: float | None = None

    def per_worker(self, generation: int, kind: Kind) -> float:
        """How many collections of a generation and kind a worker makes: for
        explicit ones, how often its `gc.collect()` calls come."""
        return self.tallies.get((generation, kind), Tally()).collections / self.workers


def load(path: Path) -> dict[str, Benchmark]:
    """Each benchmark in one CSV file, by pyperformance's name for it. pyperf's
    calibration workers are left out, and so are the processes with no benchmark's
    name, which are pyperformance's own."""
    workers: defaultdict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row["calibration"] == "0" and row["benchmark"]:
                workers[row["benchmark"], row["pid"], row["pid_epoch"]].append(row)

    counts: Counter[str] = Counter()
    tallies: defaultdict[str, dict[tuple[int, Kind], Tally]] = defaultdict(dict)
    first_examined: defaultdict[str, list[int]] = defaultdict(list)
    for (benchmark, pid, _), rows in workers.items():
        counts[benchmark] += 1
        rows.sort(key=lambda row: int(row["ts"]))
        # A worker's first row holds its first collection alone, unless gcmon lost
        # that one.
        if rows[0]["collections"] == "1":
            first_examined[benchmark].append(int(rows[0]["candidates"]))
        shutdown = _shutdown(rows)
        # The runtime keeps running totals per worker and generation. A row
        # counts what they gained since the last row read them, so a record gcmon
        # lost folds into the next one it read. A record lost after a worker's
        # last row has nothing to fold into, and no total counts it.
        read: dict[int, Tally] = {}
        for i, row in enumerate(rows):
            generation = int(row["generation"])
            totals = Tally(
                int(row["collections"]), int(row["candidates"]), int(row["collected"])
            )
            gained = totals.since(read.get(generation, Tally()))
            if min(gained) < 0:
                raise ValueError(
                    f"{benchmark} worker {pid}'s generation {generation} totals"
                    f" fall at ts {row['ts']}"
                )
            read[generation] = totals
            if i in shutdown:
                continue
            kind: Kind = "automatic" if row["auto_collect"] == "1" else "explicit"
            key = (generation, kind)
            tallies[benchmark][key] = tallies[benchmark].get(key, Tally()).add(gained)

    return {
        name: Benchmark(counts[name], tallies[name], _mean(first_examined[name]))
        for name in sorted(counts)
    }


def _shutdown(rows: list[dict[str, str]]) -> set[int]:
    """Which of a worker's rows, in the order of their ts, are shutdown's
    collections, which set no target. gcmon reads a worker from outside, once a
    tick, and a worker can end before the next, so it keeps all three of them,
    some or none. finalize_modules' two carry their own reason. `_Py_Finalize`'s
    carries gc.collect()'s, manual, so the loader takes the worker's last manual
    row for it, unless an automatic collection follows. If gcmon lost all three,
    that row is the benchmark's last gc.collect(), and the loader leaves it out
    too."""
    explicit = [i for i, row in enumerate(rows) if row["auto_collect"] == "0"]
    shutdown = {i for i in explicit if rows[i]["reason"] == SHUTDOWN}
    manual = [i for i in explicit if rows[i]["reason"] == MANUAL]
    if manual and all(row["auto_collect"] == "0" for row in rows[manual[-1] :]):
        shutdown.add(manual[-1])
    return shutdown


def _mean(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None


@cache
def load_data(directory: Path = DATA) -> dict[str, dict[str, Benchmark]]:
    """Each collector's benchmarks, from its file in data/."""
    return {name: load(directory / file) for name, file in FILES.items()}
