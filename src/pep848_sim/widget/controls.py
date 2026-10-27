"""The controls a widget shows: for each path into its request that the page names,
a label and a range of values that keeps the request valid. A path names a
workload parameter, a collector setting or a collector constant."""

from collections.abc import Iterable
from typing import NamedTuple

from pep848_sim.structures import StructureParameters
from pep848_sim.widget.request import Request, parse


class Control(NamedTuple):
    """One control, as a slider takes it: whole numbers from `min` to `max` in
    steps of `step`."""

    # Where its value sits in the request, as keys and indices joined by dots.
    path: str
    label: str
    # "kB", "share" for a share counted in thousandths, or "count" for a whole
    # number of anything else.
    unit: str
    value: int
    min: int
    max: int
    step: int


def controls(request: str, paths: Iterable[str]) -> list[Control]:
    """The controls on the given paths, with the ranges the request allows."""
    parsed = parse(request)
    return [_control(parsed, path) for path in paths]


def _control(request: Request, path: str) -> Control:
    match path.split("."):
        case ["settings", "threshold0"]:
            # A run makes between 10 and 1,000 collections, and a collection waits
            # for 1 kB at least.
            value = request.settings.threshold0
            low = max(1, -(-request.run_length // 1000))
            high = request.run_length // 10
            return _ranged(path, "threshold0", "kB", value, low, max(high, value))
        case ["settings", "threshold1"]:
            # From 1, since a widget's request refuses 0, to 40 half-spaces, four
            # times the PEP's 10, or the request's own.
            value = request.settings.threshold1
            return Control(path, "threshold1", "count", value, 1, max(40, value), 1)
        case ["settings", "threshold2"]:
            # The legacy collector's alone: the gen 1 collections before a gen 2.
            value = request.settings.threshold2
            label = "threshold2 (legacy only)"
            return Control(
                path, label, "count", value, min(0, value), max(40, value), 1
            )
        case ["constants", "initial_work_budget"]:
            # In real objects, as the PEP gives it: from twice the PEP's -100,000
            # to half of it above 0, or the request's own, by the thousand.
            value = request.constants.initial_work_budget
            low, high = min(-200_000, value), max(50_000, value)
            label = "Initial work budget (real objects)"
            return Control(path, label, "count", value, low, high, 1_000)
        case ["constants", "freed_credit"]:
            # From none to five times the PEP's 2, or the request's own.
            value = request.constants.freed_credit
            label = "Freed-credit multiplier"
            return Control(path, label, "count", value, 0, max(10, value), 1)
        case ["constants", "long_lived_ratio"]:
            # A share, in thousandths, up to the whole, or the request's own.
            share = round(request.constants.long_lived_ratio * 1000)
            label = "Long-lived ratio"
            return Control(path, label, "share", share, 0, max(1000, share), 1)
        case ["workload", "churn", "cycle_share"]:
            # A share, in thousandths, up to half the churn or the request's own.
            share = round(request.workload.churn.cycle_share * 1000)
            label = "Churn that starts a cycle"
            return Control(path, label, "share", share, 0, max(500, share), 1)
        case ["workload", "churn", "lifetime_mean"]:
            # Up to half the PEP's threshold0, or the request's own. Longer
            # lifetimes mostly outlast the nursery, and the long share already
            # draws those. In steps of 1 kB, since the short lifetimes matter most.
            mean = request.workload.churn.lifetime_mean
            label = "Churn lifetime mean"
            return Control(path, label, "kB", mean, 1, max(1000, mean), 1)
        case ["workload", "structures", index, "size"] if index.isdigit():
            structure = _structure(request, int(index))
            name = type(structure.shape).__name__
            # A build takes 1 kB for each object and each churn allocation after it,
            # and fits in the rebuild interval. One never rebuilt fits in the run,
            # unless the request's own outgrows it.
            room = structure.rebuild_interval
            if room is None:
                room = max(
                    request.run_length, structure.size * (1 + structure.build_churn)
                )
            high = room // (1 + structure.build_churn)
            return _ranged(path, f"{name} size", "kB", structure.size, 1, high)
        case ["workload", "structures", index, "rebuild_interval"] if index.isdigit():
            structure = _structure(request, int(index))
            name = type(structure.shape).__name__
            interval = structure.rebuild_interval
            if interval is None:
                raise ValueError(f"structure {index} is never rebuilt")
            # From the build to the run's end, or to the request's own interval.
            build = structure.size * (1 + structure.build_churn)
            high = max(request.run_length, interval)
            label = f"{name} rebuild interval"
            return _ranged(path, label, "kB", interval, build, high)
        case _:
            raise ValueError(f"no control {path!r}")


def _structure(request: Request, index: int) -> StructureParameters:
    structures = request.workload.structures
    if index >= len(structures):
        raise ValueError(f"no structure {index}")
    return structures[index]


def _ranged(
    path: str, label: str, unit: str, value: int, low: int, high: int
) -> Control:
    """A control from `low` to `high` on a round step about a hundredth of `high`,
    each end moved inward to the step, or outward far enough to hold `value`. A
    slider counts its steps from its least value, so a value below the rounded
    least becomes the least, and sits on a step."""
    step = 10 ** max(0, len(str(high)) - 3)
    least = min(-(-low // step) * step, value)
    most = max(least + (high - least) // step * step, least)
    if value > most:
        most = least + -(-(value - least) // step) * step
    return Control(path, label, unit, value, least, most, step)
