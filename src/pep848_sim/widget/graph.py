"""What a widget draws of a request's object graph: a sample of each structure, a
few of its objects as its shape links them, with each link that lies on a cycle
marked, so the cyclic garbage a drop leaves shows. A whole structure holds far
more objects than a page can draw: connected_components' graph holds 89,007.
"""

import json
from collections import defaultdict
from typing import NamedTuple

from pep848_sim.structures import (
    TASK_GROUPS_PATH,
    Amazon0302,
    Chains,
    Graph,
    Hierarchy,
    Own,
    Shape,
    StructureParameters,
    TaskGroups,
    Tree,
    unlinks,
)
from pep848_sim.widget.request import parse

# How far into a structure, in objects, a sample looks for children. In every
# shape the children of the objects a sample keeps come long before it.
_REACH = 4096
# The most objects a sample of a reader's own shape keeps: about as many as a
# hierarchy's sample, whatever the shape, a list as much as a tree.
_OWN_MOST = 40


class Sample(NamedTuple):
    """A few of a structure's objects, each by its index among them with its level
    below the first, and the links among them, each with whether it lies on a
    cycle."""

    objects: list[tuple[int, int]]
    links: list[tuple[int, int, bool]]


def sample(structure: StructureParameters) -> Sample:
    """The structure's first object, then the first children of each object the
    sample keeps, a level at a time, as far as its shape's extent allows."""
    shape = structure.shape
    links: list[tuple[int, int]] = []
    for i in range(min(structure.size, _REACH)):
        links += shape.links(i)
        for taken in unlinks(shape, i):
            links.remove(taken)
    children: dict[int, list[int]] = defaultdict(list)
    for source, target in links:
        children[source].append(target)
    keep, levels, most = _extent(shape)
    level = {0: 0}
    frontier = [0]
    for depth in range(1, levels + 1):
        below: list[int] = []
        for x in frontier:
            fresh = [y for y in children[x] if y not in level and y not in below]
            below.extend(fresh[:keep])
        below = below[: most - len(level)]
        if not below:
            break
        level.update(dict.fromkeys(below, depth))
        frontier = below
    inside = [(s, t) for s, t in links if s in level and t in level]
    on_cycle = _on_cycles(inside)
    return Sample(
        sorted(level.items()), [(s, t, (s, t) in on_cycle) for s, t in inside]
    )


def graph(request: str) -> str:
    """The request's structures, each with its shape, size, root, lifetime,
    rebuild interval, whether it calls `gc.collect()`, whether a frame or C code
    builds it, and its sample, and the churn's parameters, as JSON text for the widget's
    legend and drawing."""
    workload = parse(request).workload
    churn = workload.churn
    return json.dumps(
        {
            "structures": [
                {
                    "shape": _label(structure.shape),
                    "size": structure.size,
                    "root": structure.root,
                    "lifetime": structure.lifetime,
                    "rebuild_interval": structure.rebuild_interval,
                    "full_collections": structure.full_collections,
                    "built_in_frame": structure.built_in_frame,
                    "built_in_c": structure.built_in_c,
                    **sample(structure)._asdict(),
                }
                for structure in workload.structures
            ],
            "churn": {
                "cycle_share": str(churn.cycle_share),
                "cycle_size": churn.cycle_size,
                "lifetime_mean": churn.lifetime_mean,
                "long_share": str(churn.long_share),
                "long_lifetimes": churn.long_lifetimes,
            },
        }
    )


def _extent(shape: Shape) -> tuple[int, int, int]:
    """How many children of each object a sample keeps, how many levels below the
    first object it goes, and the most objects it keeps: enough to show the shape
    beside the others, as the prototype on prototype/object-graph drew them
    (#151). A reader's own shape goes as deep as its objects last."""
    if isinstance(shape, Chains):
        return 4, 3, _REACH
    if isinstance(shape, Tree):
        return 2, 3, _REACH
    if isinstance(shape, Hierarchy | Graph):
        return 6, 2, _REACH
    # Past G and its __dict__, as far as the nodes and edges _node and _adj hold.
    if isinstance(shape, Amazon0302):
        return 6, 4, _REACH
    # Down the path to the loop, then as far as the first tasks' children.
    if isinstance(shape, TaskGroups):
        return 2, TASK_GROUPS_PATH + 6, _REACH
    if isinstance(shape, Own):
        return 4, _OWN_MOST, _OWN_MOST
    # Each ring as far as six objects round it.
    return 10, min(shape.length, 6), _REACH


def _label(shape: Shape) -> str:
    """A shape as the legend names it."""
    if isinstance(shape, Chains):
        return f"{shape.width} chains"
    if isinstance(shape, Tree):
        return "a tree with parent pointers"
    if isinstance(shape, Hierarchy):
        return f"a hierarchy of {shape.branches} branches"
    if isinstance(shape, Graph):
        return f"a graph of {shape.edges} edges a node"
    if isinstance(shape, Amazon0302):
        return "networkx's amazon0302 graph"
    if isinstance(shape, TaskGroups):
        return "asyncio's tasks in TaskGroups"
    if isinstance(shape, Own):
        return "a shape of your own"
    return f"rings of {shape.length} object{'' if shape.length == 1 else 's'}"


def _on_cycles(links: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """The links that lie on a cycle: those within one strongly connected
    component, which Tarjan's walk finds, a link from an object to itself
    included."""
    out: dict[int, list[int]] = defaultdict(list)
    for source, target in links:
        out[source].append(target)
    index: dict[int, int] = {}
    low: dict[int, int] = {}
    stack: list[int] = []
    component: dict[int, int] = {}

    def visit(v: int) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        for w in out[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w not in component:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                component[w] = v
                if w == v:
                    break

    for source, _ in links:
        if source not in index:
            visit(source)
    return {(s, t) for s, t in links if component[s] == component[t]}
