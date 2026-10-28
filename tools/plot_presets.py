"""Each preset's collections under both collectors beside its benchmark's
workers', one collection at a time, as the plot.json that `just site` writes and
the presets page draws (ADR 0021). compare_presets.py sets their averages side by
side, where a preset can match its benchmark's mean and still drift from it over
the run.

Every count is in real objects, by the run's constants. A point stands at the
collection's number in its worker, counting every collection before it: the trace
has no allocation clock.
"""

import json
from collections.abc import Iterable
from pathlib import Path

from benchmarks import DATA, FILES, Collection, Kind, Tally, read_workers
from compare_presets import COLLECTORS, FILED, run_preset
from pep848_sim.collectors.collector import Constants, Record
from pep848_sim.presets import PRESETS

# The generation each collector's old collections file in, whose work the plot
# draws: the incremental collector's increments and the legacy one's gen 2, each
# with the full collections. The branch's rows carry increment_size on the
# increments alone, so elsewhere only the run draws its work.
OLD = {"incremental": 1, "legacy": 2}

# A collection as the page draws it: its number in its worker, its panel, and its
# series. A series the collection has no value for is left out.
type Point = dict[str, int | float | str]

# A worker's collections as plot.json holds them: a column to a series.
type Columns = dict[str, list[int | float | None]]

# The series a point can carry besides its number and its panel.
SERIES = ("examined", "freed", "yield", "work", "budget")


def collections(records: Iterable[Record], constants: Constants) -> list[Collection]:
    """A run's records as one worker's collections, as the branch's rows would
    hold them: what each examined and freed, all it did as its work, and the work
    budget before it, which is the record before's or the constants' initial one."""
    found = []
    budget = constants.simulated(constants.initial_work_budget)
    for record in records:
        filed = FILED[record.kind]
        generation, kind = filed if filed is not None else (2, "explicit")
        gained = Tally(
            1,
            constants.real(record.survived + record.freed),
            constants.real(record.freed),
        )
        found.append(
            Collection(
                generation,
                kind,
                gained,
                constants.real(record.work),
                constants.real(budget),
                filed is None,
            )
        )
        budget = record.work_to_do
    return found


def panel(generation: int, kind: Kind) -> str:
    return f"gen {generation} {kind}"


# Every panel a collection can stand in, young to old, as plot.json names them.
PANELS = sorted({panel(*filed) for filed in FILED.values() if filed is not None})


def points(worker: Iterable[Collection], collector: str) -> list[Point]:
    """A worker's collections as the page draws them, shutdown's left out: what
    each examined and freed, its panel's running yield, its work if it is an old
    collection, and the work budget before it under the incremental collector. A
    row that folds collections gcmon lost draws what they examined and freed on
    average, at the last one's number."""
    drawn: list[Point] = []
    number = 0
    totals: dict[str, Tally] = {}
    for collection in worker:
        number += collection.gained.collections
        if collection.shutdown:
            continue
        name = panel(collection.generation, collection.kind)
        totals[name] = totals.get(name, Tally()).add(collection.gained)
        point: Point = {"n": number, "panel": name}
        if collection.gained.collections:
            point["examined"] = (
                collection.gained.candidates / collection.gained.collections
            )
            point["freed"] = collection.gained.collected / collection.gained.collections
        running = totals[name].yield_
        if running is not None:
            point["yield"] = running
        if (
            collection.generation >= OLD[collector]
            and collection.increment_size is not None
        ):
            point["work"] = collection.increment_size
        if collector == "incremental" and collection.old_work is not None:
            point["budget"] = collection.old_work
        drawn.append(point)
    return drawn


def columns(drawn: list[Point]) -> Columns:
    """A worker's points as columns: each panel by its place in PANELS, null where
    a point has no value, and no column for a series no point has. A mean takes
    four significant digits, which is more than the page can draw."""
    found: Columns = {
        "n": [int(point["n"]) for point in drawn],
        "panel": [PANELS.index(str(point["panel"])) for point in drawn],
    }
    for series in SERIES:
        column = [_compact(point.get(series)) for point in drawn]
        if any(value is not None for value in column):
            found[series] = column
    return found


def _compact(value: int | float | str | None) -> int | float | None:
    if value is None or isinstance(value, str):
        return None
    if isinstance(value, int) or value.is_integer():
        return int(value)
    return float(f"{value:.4g}")


def plot() -> dict[str, object]:
    """Each preset under each collector, its benchmark's workers and its run, as
    plot.json holds them."""
    constants = Constants()
    data = {name: read_workers(DATA / file) for name, file in FILES.items()}
    plots: list[dict[str, object]] = []
    for name, preset in PRESETS.items():
        for collector, make in COLLECTORS.items():
            run = collections(run_preset(preset, make), constants)
            plots.append(
                {
                    "preset": name,
                    "collector": collector,
                    "workers": [
                        columns(points(worker, collector))
                        for worker in data[collector][preset.benchmark]
                    ],
                    "run": columns(points(run, collector)),
                }
            )
    return {"panels": PANELS, "plots": plots}


def write(path: Path) -> None:
    """Write plot.json to `path`."""
    path.write_text(json.dumps(plot(), separators=(",", ":")), encoding="utf-8")
