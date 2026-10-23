"""Write mock files in the layout of gcmon's CSV extract into data/: a table per
collector and its metadata beside it. They stand in for the rerun of pyperformance
(#117), so the loader and what reads it can land first. The script makes up every
number in them. Delete it once the rerun's files replace them.
"""

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from random import Random
from typing import NamedTuple

from benchmarks import COLLECTORS, DATA

FIELDS = (
    "benchmark",
    "worker",
    "calibration",
    "ts",
    "generation",
    "auto_collect",
    "collections",
    "candidates",
    "collected",
    "heap_size",
    "heap_size_stop",
    "old_work",
    "increment_size",
    "survivor_count",
)

# Workers per benchmark, and calibration workers beside them.
WORKERS = 3
CALIBRATION_WORKERS = 1

# One record in this many goes unread, and folds into the next.
LOST = 40


class Profile(NamedTuple):
    """What a mock worker of one benchmark does, in real objects."""

    # Automatic young collections the benchmark's loops trigger.
    young: int
    # Loops that call `gc.collect()` before their build and after their drop.
    loops: int
    # Cyclic garbage each of those loops leaves.
    loop_garbage: int
    # The share of a young collection's candidates that is cyclic garbage.
    young_garbage: float
    # What the benchmark's imports and data add to the heap after start-up.
    data: int
    # The share of the heap that shutdown's first full collection frees.
    shutdown: float


PROFILES = {
    "create_gc_cycles": Profile(0, 64, 2100, 0.0, 500, 0.3),
    "json_loads": Profile(8, 0, 0, 0.0, 4000, 0.25),
    "xml_etree_parse": Profile(24, 0, 0, 0.001, 20_000, 0.2),
    "async_tree_io_tg": Profile(80, 0, 0, 0.0002, 60_000, 0.35),
    "connected_components": Profile(32, 0, 0, 0.0003, 30_000, 0.95),
}


def worker_rows(
    rng: Random,
    collector: str,
    benchmark: str,
    worker: int,
    calibration: bool,
) -> Iterator[dict[str, object]]:
    """The rows gcmon reads from one worker: start-up, the loops and shutdown."""
    profile = PROFILES[benchmark]
    if calibration:
        profile = profile._replace(young=profile.young // 4, loops=profile.loops // 4)
    totals = {generation: [0, 0, 0] for generation in (0, 1, 2)}
    heap = rng.randint(10_000, 11_000)
    # Each worker starts on a ts of its own, far past the last one's end.
    ts = worker * 10**12

    def collect(
        generation: int, automatic: bool, candidates: int, collected: int
    ) -> dict[str, object]:
        nonlocal heap, ts
        ts += rng.randint(100_000, 10_000_000)
        for index, count in enumerate((1, candidates, collected)):
            totals[generation][index] += count
        incremental_old = collector == "incremental" and generation == 1
        row: dict[str, object] = {
            "benchmark": benchmark,
            "worker": worker,
            "calibration": int(calibration),
            "ts": ts,
            "generation": generation,
            "auto_collect": int(automatic),
            "collections": totals[generation][0],
            "candidates": totals[generation][1],
            "collected": totals[generation][2],
            "heap_size": heap,
            "heap_size_stop": heap - collected,
            "old_work": rng.randint(0, 8000) if incremental_old else "",
            "increment_size": candidates if incremental_old else "",
            "survivor_count": candidates - collected,
        }
        heap -= collected
        return row

    def young() -> dict[str, object]:
        nonlocal heap
        candidates = rng.randint(1500, 3000)
        garbage = int(candidates * profile.young_garbage * 2 * rng.random())
        row = collect(0, True, candidates, garbage)
        heap += candidates - garbage
        return row

    rows = [young(), young()]
    heap += profile.data
    for index in range(profile.young):
        rows.append(young())
        if collector == "incremental" and rng.random() < 0.5:
            increment = rng.randint(200, 4000)
            garbage = int(increment * profile.young_garbage * rng.random())
            rows.append(collect(1, True, increment, garbage))
        elif collector == "legacy" and index % 10 == 9:
            candidates = rng.randint(5000, 20_000)
            garbage = int(candidates * profile.young_garbage * rng.random())
            rows.append(collect(1, True, candidates, garbage))
            if index % 100 == 99:
                rows.append(collect(2, True, heap, heap // 1000))
    for _ in range(profile.loops):
        rows.append(collect(2, False, heap, 0))
        heap += profile.loop_garbage
        rows.append(collect(2, False, heap, profile.loop_garbage))

    # Shutdown's two full collections come after gcmon's last poll: it reads the
    # first at most, and loses the second for good (gcmon#229).
    first = collect(2, False, heap, int(heap * profile.shutdown))
    collect(2, False, heap, heap // 100)
    yield from (row for row in rows if rng.randrange(LOST))
    if rng.random() < 0.5:
        yield first


def write(directory: Path, collector: str) -> None:
    """Write one collector's table and metadata, the same each time."""
    rng = Random(collector)
    workers = (
        (benchmark, calibration)
        for benchmark in PROFILES
        for calibration in [True] * CALIBRATION_WORKERS + [False] * WORKERS
    )
    with (directory / f"{collector}.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        table = csv.DictWriter(file, FIELDS, lineterminator="\n")
        table.writeheader()
        for worker, (benchmark, calibration) in enumerate(workers, start=101):
            table.writerows(worker_rows(rng, collector, benchmark, worker, calibration))
    metadata = {
        "mock": True,
        "collector": collector,
        "commit": None,
        "thresholds": [2000, 10, 10],
        "gcmon": None,
        "pyperformance": None,
        "date": None,
        "trace_sha256": None,
    }
    (directory / f"{collector}.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline=""
    )


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    for collector in COLLECTORS:
        write(DATA, collector)
