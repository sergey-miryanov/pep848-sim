"""The controls a widget shows: for each path into its request that the page names,
a label and a range of values that keeps the request valid."""

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
    # "kB", or "share" for a share counted in thousandths.
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
            # A run makes between 10 and 1,000 collections.
            value = request.settings.threshold0
            low, high = -(-request.run_length // 1000), request.run_length // 10
            return _ranged(path, "threshold0", "kB", value, low, max(high, value))
        case ["workload", "churn", "cycle_share"]:
            # A share, in thousandths, up to half the churn or the request's own.
            share = round(request.workload.churn.cycle_share * 1000)
            label = "Churn that starts a cycle"
            return Control(path, label, "share", share, 0, max(500, share), 1)
        case ["workload", "churn", "lifetime_mean"]:
            # Up to half the PEP's threshold0, or the request's own. Longer lives
            # mostly outlast the nursery, where the long share already draws them.
            # Every kB, since the short lives matter most.
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
    each end moved inward to the step."""
    step = 10 ** max(0, len(str(high)) - 3)
    least = -(-low // step) * step
    return Control(
        path, label, unit, value, least, max(least, high // step * step), step
    )
