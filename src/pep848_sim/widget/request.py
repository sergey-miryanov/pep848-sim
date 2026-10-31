"""What a widget asks the simulator for: a workload, collector settings, a run length
and the records each part of a run holds, as JSON text, with the collector constants
and the real object's size where the playground changes them. A request can name a
preset in place of its workload and run length, so that a preset's numbers live in
one place, with changes to its spelled-out fields where the guide needs a variant, or
carry the playground's Python source of all of them. The worker passes
the text on as the page sent it, so no browser object reaches the simulator.
"""

import json
from collections.abc import Collection, Iterator
from dataclasses import asdict, fields
from fractions import Fraction
from functools import lru_cache
from typing import Any, NamedTuple

from pep848_sim.collectors.collector import CollectorSettings, Constants, Record
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.presets import PRESETS
from pep848_sim.run import check_every, run
from pep848_sim.structures import (
    Amazon0302,
    Chains,
    Graph,
    Hierarchy,
    Own,
    Rings,
    Shape,
    StructureParameters,
    TaskGroups,
    Tree,
)
from pep848_sim.widget import source
from pep848_sim.workload import ChurnParameters, WorkloadParameters


class Request(NamedTuple):
    workload: WorkloadParameters
    settings: CollectorSettings
    run_length: int
    every: int
    constants: Constants = Constants()


# The field a request may leave out, for its defaults.
_OPTIONAL = ("constants",)
# The fields of a request that names a preset, which brings its workload and run
# length. Its changes, which it may leave out too, map a path into the spelled-out
# request, as a control's, to the value it takes there.
_PRESET_FIELDS = ("preset", "settings", "every", "changes", *_OPTIONAL)
# The fields of a request that carries a workload source, which sets its
# workload, collector settings, run length and constants.
_SOURCE_FIELDS = ("source", "every")


# The worker reads each request four times, for its controls, its spelled-out
# form, its object graph and its runs. Keeping the last few runs a source and
# checks a shape of the reader's own once for all four, and each reading gets the
# same workload, whatever the source draws.
@lru_cache(maxsize=16)
def parse(request: str) -> Request:
    """The request a widget sends, refused unless it holds every field but the
    constants, and no other."""
    values = json.loads(request)
    # run() checks it when the worker reads the first part, so the request
    # refuses it before either run starts.
    check_every(values.get("every", 1))
    if "source" in values:
        values = _values(values, _SOURCE_FIELDS, "request")
        workload, settings, run_length, constants = source.read(values["source"])
        for structure in workload.structures:
            _check(structure)
        return Request(workload, settings, run_length, values["every"], constants)
    if "preset" in values:
        values = _values(values, _PRESET_FIELDS, "request", (*_OPTIONAL, "changes"))
        preset = PRESETS.get(values["preset"])
        if preset is None:
            raise ValueError(f"no preset {values['preset']!r}")
        named = Request(
            preset.workload,
            _settings(values["settings"]),
            preset.run_length,
            values["every"],
            _constants(values),
        )
        if "changes" not in values:
            return named
        spelled = json.loads(dump(named))
        for path, value in values["changes"].items():
            _change(spelled, path, value)
        return parse(json.dumps(spelled))
    values = _values(values, Request._fields, "request", _OPTIONAL)
    return Request(
        _workload(values["workload"]),
        _settings(values["settings"]),
        values["run_length"],
        values["every"],
        _constants(values),
    )


def expand(request: str) -> str:
    """The request with any preset it names spelled out: the preset's workload and
    run length, which the widget's controls then edit, and the constants."""
    return dump(parse(request))


def dump(request: Request) -> str:
    """A request as JSON text, as `parse` reads it."""
    workload = request.workload
    churn = workload.churn
    return json.dumps(
        {
            "workload": {
                "churn": asdict(churn)
                | {
                    "cycle_share": str(churn.cycle_share),
                    "long_share": str(churn.long_share),
                    "long_lifetimes": list(churn.long_lifetimes),
                },
                "structures": [
                    asdict(structure)
                    | {
                        "shape": _named(structure.shape),
                        "build_churn": _written(structure.build_churn),
                    }
                    for structure in workload.structures
                ],
                "seed": workload.seed,
                "shutdown": workload.shutdown,
            },
            "settings": asdict(request.settings),
            "run_length": request.run_length,
            "every": request.every,
            "constants": asdict(request.constants)
            | {"long_lived_ratio": str(request.constants.long_lived_ratio)},
        }
    )


def runs(request: str) -> tuple[Iterator[list[Record]], Iterator[list[Record]]]:
    """The two runs a widget compares, legacy first."""
    workload, settings, run_length, every, constants = parse(request)
    return (
        run(workload, LegacyCollector, settings, run_length, every, constants),
        run(workload, IncrementalCollector, settings, run_length, every, constants),
    )


def _names(parameters: type) -> list[str]:
    return [field.name for field in fields(parameters)]


def _settings(values: dict[str, Any]) -> CollectorSettings:
    return CollectorSettings(**_values(values, _names(CollectorSettings), "settings"))


def _constants(values: dict[str, Any]) -> Constants:
    """The constants a request holds, or the defaults where it holds none."""
    if "constants" not in values:
        return Constants()
    constants = _values(values["constants"], _names(Constants), "constants")
    return Constants(
        **constants | {"long_lived_ratio": Fraction(constants["long_lived_ratio"])}
    )


def _values(
    values: dict[str, Any],
    names: Collection[str],
    what: str,
    optional: Collection[str] = (),
) -> dict[str, Any]:
    """The values of `what`, which holds each field named but the optional ones,
    and no other."""
    for name in values:
        if name not in names:
            raise ValueError(f"{what} has no field {name!r}")
    for name in names:
        if name not in values and name not in optional:
            raise ValueError(f"{what} lacks {name!r}")
    return values


def _change(spelled: dict[str, Any], path: str, value: Any) -> None:
    """Set the field at a path of keys and indices joined by dots, as a control's,
    refused unless the spelled-out request has it."""
    *keys, last = path.split(".")
    held: Any = spelled
    try:
        for key in keys:
            held = held[int(key)] if isinstance(held, list) else held[key]
        if isinstance(held, list):
            held[int(last)] = value
        elif last in held:
            held[last] = value
        else:
            raise KeyError(last)
    except KeyError, IndexError, ValueError, TypeError:
        raise ValueError(f"a preset's request has no field {path!r}") from None


def _workload(values: dict[str, Any]) -> WorkloadParameters:
    values = _values(values, _names(WorkloadParameters), "workload")
    churn = _values(values["churn"], _names(ChurnParameters), "churn")
    return WorkloadParameters(
        ChurnParameters(
            **churn
            | {
                "cycle_share": Fraction(churn["cycle_share"]),
                "long_share": Fraction(churn["long_share"]),
                "long_lifetimes": tuple(churn["long_lifetimes"]),
            }
        ),
        tuple(_structure(structure) for structure in values["structures"]),
        values["seed"],
        values["shutdown"],
    )


def _structure(values: dict[str, Any]) -> StructureParameters:
    # Links the playground wrote before a frame or C code could build a structure,
    # or before a repeating one could wait or skip, leave those fields out.
    values = _values(
        values,
        _names(StructureParameters),
        "structure",
        optional=["built_in_frame", "built_in_c", "delay", "skips_while_busy"],
    )
    return _check(
        StructureParameters(
            **values
            | {
                "shape": _shape(values["shape"]),
                "build_churn": _fraction(values["build_churn"], "a build's churn"),
            }
        )
    )


def _fraction(value: Any, what: str) -> Fraction:
    """A whole number, or a fraction as text such as "1/4"."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError(f"{what} of {value!r} is no number")
    try:
        return Fraction(value)
    except ValueError:
        raise ValueError(f"{what} of {value!r} is no number") from None


def _written(churn: int | Fraction) -> int | str:
    """A build's churn as a request holds it: a whole one as a number, and a
    fraction as text, as a share is."""
    return churn if isinstance(churn, int) else str(churn)


def _check(structure: StructureParameters) -> StructureParameters:
    # A reader's own links show their faults before a run starts.
    if isinstance(structure.shape, Own):
        structure.shape.check(structure.size)
    return structure


def _named(shape: Shape) -> str | dict[str, int] | dict[str, str]:
    """A shape as a request names it."""
    if isinstance(shape, Tree):
        return "tree"
    if isinstance(shape, Amazon0302):
        return "amazon0302"
    if isinstance(shape, TaskGroups):
        return "task_groups"
    if isinstance(shape, Chains):
        return {"chains": shape.width}
    if isinstance(shape, Hierarchy):
        return {"hierarchy": shape.branches}
    if isinstance(shape, Graph):
        return {"graph": shape.edges}
    if isinstance(shape, Own):
        return {"own": shape.code}
    return {"rings": shape.length}


def _shape(shape: Any) -> Shape:
    """A shape: "tree", "amazon0302", "task_groups", {"chains": width},
    {"hierarchy": branches}, {"graph": edges}, {"rings": length}, or {"own": code}
    for the reader's own."""
    if shape == "tree":
        return Tree()
    if shape == "amazon0302":
        return Amazon0302()
    if shape == "task_groups":
        return TaskGroups()
    if isinstance(shape, dict) and list(shape) == ["chains"]:
        return Chains(shape["chains"])
    if isinstance(shape, dict) and list(shape) == ["hierarchy"]:
        return Hierarchy(shape["hierarchy"])
    if isinstance(shape, dict) and list(shape) == ["graph"]:
        return Graph(shape["graph"])
    if isinstance(shape, dict) and list(shape) == ["rings"]:
        return Rings(shape["rings"])
    if isinstance(shape, dict) and list(shape) == ["own"]:
        if not isinstance(shape["own"], str):
            raise ValueError("your shape's code is not text")
        return Own(shape["own"])
    raise ValueError(f"no shape {shape!r}")
