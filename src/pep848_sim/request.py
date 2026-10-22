"""What a widget asks the simulator for: a workload, collector settings, a run length
and the records each part of a run holds, as JSON text. The worker passes the text
on as the page sent it, so no browser object reaches the simulator.
"""

import json
from collections.abc import Collection, Iterator
from dataclasses import fields
from fractions import Fraction
from typing import Any, get_args

from pep848_sim.collector import CollectorSettings, Record
from pep848_sim.incremental import IncrementalCollector
from pep848_sim.legacy import LegacyCollector
from pep848_sim.run import run
from pep848_sim.structures import Chains, Root, Shape, StructureParameters, Tree
from pep848_sim.workload import ChurnParameters, WorkloadParameters


def runs(request: str) -> tuple[Iterator[list[Record]], Iterator[list[Record]]]:
    """The two runs a widget compares, legacy first."""
    values = _values(
        json.loads(request), ("workload", "settings", "run_length", "every"), "request"
    )
    workload = _workload(values["workload"])
    settings = CollectorSettings(
        **_values(values["settings"], _names(CollectorSettings), "settings")
    )
    run_length, every = values["run_length"], values["every"]
    return (
        run(workload, LegacyCollector, settings, run_length, every),
        run(workload, IncrementalCollector, settings, run_length, every),
    )


def _names(parameters: type) -> list[str]:
    return [field.name for field in fields(parameters)]


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
    )


def _structure(values: dict[str, Any]) -> StructureParameters:
    values = _values(values, _names(StructureParameters), "structure")
    if values["root"] not in get_args(Root.__value__):
        raise ValueError(f"no root {values['root']!r}")
    return StructureParameters(**values | {"shape": _shape(values["shape"])})


def _shape(shape: Any) -> Shape:
    """A shape: "tree", or {"chains": width}."""
    if shape == "tree":
        return Tree()
    if isinstance(shape, dict) and list(shape) == ["chains"]:
        return Chains(shape["chains"])
    raise ValueError(f"no shape {shape!r}")
