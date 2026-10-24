"""What a widget asks the simulator for: a workload, collector settings, a run length
and the records each part of a run holds, as JSON text. A request can name a preset
in place of its workload and run length, so that a preset's numbers live in one
place. The worker passes the text on as the page sent it, so no browser object
reaches the simulator.
"""

import json
from collections.abc import Collection, Iterator
from dataclasses import asdict, fields
from fractions import Fraction
from typing import Any, NamedTuple, get_args

from pep848_sim.collectors.collector import CollectorSettings, Record
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.presets import PRESETS
from pep848_sim.run import run
from pep848_sim.structures import (
    Chains,
    Graph,
    Hierarchy,
    Rings,
    Root,
    Shape,
    StructureParameters,
    Tree,
)
from pep848_sim.workload import ChurnParameters, WorkloadParameters


class Request(NamedTuple):
    workload: WorkloadParameters
    settings: CollectorSettings
    run_length: int
    every: int


# The fields of a request that names a preset, which brings its workload and run
# length.
_PRESET_FIELDS = ("preset", "settings", "every")


def parse(request: str) -> Request:
    """The request a widget sends, refused unless it holds every field and no other."""
    values = json.loads(request)
    if "preset" in values:
        values = _values(values, _PRESET_FIELDS, "request")
        preset = PRESETS.get(values["preset"])
        if preset is None:
            raise ValueError(f"no preset {values['preset']!r}")
        return Request(
            preset.workload,
            _settings(values["settings"]),
            preset.run_length,
            values["every"],
        )
    values = _values(values, Request._fields, "request")
    return Request(
        _workload(values["workload"]),
        _settings(values["settings"]),
        values["run_length"],
        values["every"],
    )


def expand(request: str) -> str:
    """The request with any preset it names spelled out: the preset's workload and
    run length, which the widget's controls then edit."""
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
                    asdict(structure) | {"shape": _named(structure.shape)}
                    for structure in workload.structures
                ],
                "seed": workload.seed,
                "shutdown": workload.shutdown,
            },
            "settings": asdict(request.settings),
            "run_length": request.run_length,
            "every": request.every,
        }
    )


def runs(request: str) -> tuple[Iterator[list[Record]], Iterator[list[Record]]]:
    """The two runs a widget compares, legacy first."""
    workload, settings, run_length, every = parse(request)
    return (
        run(workload, LegacyCollector, settings, run_length, every),
        run(workload, IncrementalCollector, settings, run_length, every),
    )


def _names(parameters: type) -> list[str]:
    return [field.name for field in fields(parameters)]


def _settings(values: dict[str, Any]) -> CollectorSettings:
    return CollectorSettings(**_values(values, _names(CollectorSettings), "settings"))


def _values(
    values: dict[str, Any], names: Collection[str], what: str
) -> dict[str, Any]:
    """The values of `what`, which holds each field named and no other."""
    for name in values:
        if name not in names:
            raise ValueError(f"{what} has no field {name!r}")
    for name in names:
        if name not in values:
            raise ValueError(f"{what} lacks {name!r}")
    return values


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
    values = _values(values, _names(StructureParameters), "structure")
    if values["root"] not in get_args(Root.__value__):
        raise ValueError(f"no root {values['root']!r}")
    return StructureParameters(**values | {"shape": _shape(values["shape"])})


def _named(shape: Shape) -> str | dict[str, int]:
    """A shape as a request names it."""
    if isinstance(shape, Tree):
        return "tree"
    if isinstance(shape, Chains):
        return {"chains": shape.width}
    if isinstance(shape, Hierarchy):
        return {"hierarchy": shape.branches}
    if isinstance(shape, Graph):
        return {"graph": shape.edges}
    return {"rings": shape.length}


def _shape(shape: Any) -> Shape:
    """A shape: "tree", {"chains": width}, {"hierarchy": branches},
    {"graph": edges} or {"rings": length}."""
    if shape == "tree":
        return Tree()
    if isinstance(shape, dict) and list(shape) == ["chains"]:
        return Chains(shape["chains"])
    if isinstance(shape, dict) and list(shape) == ["hierarchy"]:
        return Hierarchy(shape["hierarchy"])
    if isinstance(shape, dict) and list(shape) == ["graph"]:
        return Graph(shape["graph"])
    if isinstance(shape, dict) and list(shape) == ["rings"]:
        return Rings(shape["rings"])
    raise ValueError(f"no shape {shape!r}")
