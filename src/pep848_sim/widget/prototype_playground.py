"""PROTOTYPE, not for main (#153, #155): what site/prototype-playground.js needs
from the simulator, patched in when the worker imports this module.

- A shape of the reader's own: Python code that defines `links(i)`, which a
  request names as {"own": code}. The simulator counts the cyclic garbage a drop
  leaves by refcounting the structure's own links, and the object graph samples
  it three children and four levels deep.
- A workload written as Python source, which a request carries as
  {"source": text, "every": n}.
"""

import json
from collections import defaultdict
from collections.abc import Callable
from fractions import Fraction
from typing import Any

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import (
    Chains,
    Graph,
    Hierarchy,
    Rings,
    Root,
    StructureParameters,
    Tree,
)
from pep848_sim.widget import controls, graph, request
from pep848_sim.workload import ChurnParameters, WorkloadParameters

type Links = Callable[[int], list[tuple[int, int]]]


class Own:
    """A shape of the reader's own, from code that defines `links(i)` or from a
    function the source defines."""

    def __init__(self, code: str | Links, name: str = "a shape of your own") -> None:
        if callable(code):
            self.code = f"# from the source: {code.__name__}"
            self._links = code
        else:
            namespace: dict[str, Any] = {}
            exec(code, namespace)
            if "links" not in namespace:
                raise ValueError("your shape's code defines no links(i)")
            self.code = code
            self._links = namespace["links"]
        self.name = name
        self._garbage: dict[int, int] = {}

    def links(self, i: int) -> list[tuple[int, int]]:
        made = self._links(i)
        for link in made:
            if not (
                isinstance(link, tuple | list)
                and len(link) == 2
                and all(isinstance(x, int) and 0 <= x <= i for x in link)
            ):
                raise ValueError(
                    f"links({i}) gives {link!r}: a link joins two of objects 0 to {i}"
                )
        return [(source, target) for source, target in made]

    def cyclic_garbage(self, size: int) -> int:
        """What refcounting leaves of a dropped structure of this size: the objects
        on a cycle, and what they hold."""
        if size not in self._garbage:
            out: dict[int, list[int]] = defaultdict(list)
            count = [0] * size
            for i in range(size):
                for source, target in self.links(i):
                    out[source].append(target)
                    count[target] += 1
            freed = [x for x in range(size) if not count[x]]
            alive = size - len(freed)
            while freed:
                x = freed.pop()
                for target in out[x]:
                    count[target] -= 1
                    if not count[target]:
                        freed.append(target)
                        alive -= 1
            self._garbage[size] = alive
        return self._garbage[size]


def _structure(
    shape: Any,
    size: int,
    root: Root = "frame",
    lifetime: int | None = None,
    rebuild_interval: int | None = None,
    build_churn: int = 0,
    full_collections: bool = False,
) -> StructureParameters:
    return StructureParameters(
        shape, size, root, lifetime, rebuild_interval, build_churn, full_collections
    )


def _churn(
    lifetime_mean: int,
    cycle_share: str = "0",
    cycle_size: int = 2,
    long_share: str = "0",
    long_lifetimes: tuple[int, int] = (1, 1),
) -> ChurnParameters:
    return ChurnParameters(
        Fraction(cycle_share),
        cycle_size,
        lifetime_mean,
        Fraction(long_share),
        tuple(long_lifetimes),
    )


def from_source(text: str, every: int) -> request.Request:
    namespace: dict[str, Any] = {
        "Chains": Chains,
        "Tree": Tree,
        "Hierarchy": Hierarchy,
        "Graph": Graph,
        "Rings": Rings,
        "Own": Own,
        "Structure": _structure,
        "Churn": _churn,
        "Settings": CollectorSettings,
    }
    exec(text, namespace)
    for name in ("churn", "structures", "run_length"):
        if name not in namespace:
            raise ValueError(f"the source sets no {name}")
    workload = WorkloadParameters(
        namespace["churn"],
        tuple(namespace["structures"]),
        namespace.get("seed", 848),
        namespace.get("shutdown", False),
    )
    settings = namespace.get("settings", CollectorSettings())
    return request.Request(workload, settings, namespace["run_length"], every)


_parse = request.parse


def _parse_source(text: str) -> request.Request:
    values = json.loads(text)
    if isinstance(values, dict) and "source" in values:
        return from_source(values["source"], values.get("every", 5))
    return _parse(text)


_shape = request._shape


def _own_shape(shape: Any) -> Any:
    if isinstance(shape, dict) and list(shape) == ["own"]:
        return Own(shape["own"])
    return _shape(shape)


_named = request._named


def _own_named(shape: Any) -> Any:
    return {"own": shape.code} if isinstance(shape, Own) else _named(shape)


_extent = graph._extent


def _own_extent(shape: Any) -> tuple[int, int]:
    return (3, 4) if isinstance(shape, Own) else _extent(shape)


_label = graph._label


def _own_label(shape: Any) -> str:
    return shape.name if isinstance(shape, Own) else _label(shape)


request.parse = _parse_source
graph.parse = _parse_source
controls.parse = _parse_source
request._shape = _own_shape
request._named = _own_named
graph._extent = _own_extent
graph._label = _own_label
