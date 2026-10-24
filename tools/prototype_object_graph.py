"""PROTOTYPE, not for main (#151): write a sample of each preset's object graph to
site/prototype-object-graph.json, for site/prototype-object-graph.js to draw.

For each structure: a sample of its objects, as its shape links them, a few
children to each object and a few levels deep, the links among them, which of
those lie on a cycle, and how many children each sampled object holds beyond the
sample. Also its builds and drops on the allocation clock, from a run of the
workload, and the churn's parameters.
"""

import json
from collections import defaultdict
from pathlib import Path

from pep848_sim.collectors.collector import Collector
from pep848_sim.collectors.heap import Heap
from pep848_sim.presets import PRESETS
from pep848_sim.structures import Graph, Hierarchy, Rings, StructureParameters
from pep848_sim.workload import Workload

OUT = Path(__file__).parent.parent / "site" / "prototype-object-graph.json"

LABELS = {
    "create_gc_cycles": ["start-up: chains", "start-up: tree", "rings"],
    "json_loads": ["start-up: chains", "start-up: tree"],
    "xml_etree_parse": [
        "start-up: chains",
        "start-up: tree",
        "the value's tree",
        "parsed trees",
    ],
    "async_tree_io_tg": ["start-up: chains", "start-up: tree", "task tree"],
    "connected_components": ["start-up: chains", "start-up: tree", "graph"],
}
# The most builds each structure's timeline keeps.
MOST_BUILDS = 1000


def sample(structure: StructureParameters) -> dict[str, object]:
    shape = structure.shape
    keep, depth = 4, 3
    if isinstance(shape, Graph):
        keep, depth = 6, 2
    elif isinstance(shape, Rings):
        keep, depth = 10, 1
    elif isinstance(shape, Hierarchy):
        keep, depth = 6, 2
    reach = structure.size
    links = [link for i in range(reach) for link in shape.links(i)]
    children: dict[int, list[int]] = defaultdict(list)
    for source, target in links:
        children[source].append(target)
    # A walk from the root that keeps the first few children of each object.
    level = {0: 0}
    frontier = [0]
    while frontier:
        nxt = []
        for x in frontier:
            if level[x] == depth:
                continue
            kept = 0
            for y in children[x]:
                if y in level or kept == keep:
                    continue
                level[y] = level[x] + 1
                nxt.append(y)
                kept += 1
        frontier = nxt
    nodes = sorted(level)
    inside = [(s, t) for s, t in links if s in level and t in level]
    on_cycle = cycles(nodes, inside)
    more = {x: sum(1 for y in children[x] if y not in level and y > x) for x in nodes}
    return {
        "nodes": [{"id": x, "level": level[x], "more": more[x]} for x in nodes],
        "links": [
            {"source": s, "target": t, "cycle": (s, t) in on_cycle} for s, t in inside
        ],
    }


def cycles(nodes: list[int], links: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """The links that lie on a cycle: those inside one strongly connected
    component, Tarjan's way."""
    out: dict[int, list[int]] = defaultdict(list)
    for s, t in links:
        out[s].append(t)
    index: dict[int, int] = {}
    low: dict[int, int] = {}
    stack: list[int] = []
    on: set[int] = set()
    component: dict[int, int] = {}
    counter = [0]

    def visit(v: int) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in out[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                on.discard(w)
                component[w] = v
                if w == v:
                    break

    for v in nodes:
        if v not in index:
            visit(v)
    return {(s, t) for s, t in links if component[s] == component[t]}


def timeline(name: str) -> list[list[list[int]]]:
    """Each structure's builds, as [first kB, last kB, drop kB or the run's end]."""
    preset = PRESETS[name]
    workload = Workload(Heap(Collector()), preset.workload)
    workload.run_to(preset.run_length)
    spans: list[list[list[int]]] = [[] for _ in preset.workload.structures]
    for i, first, last in workload.builds:
        lifetime = preset.workload.structures[i].lifetime
        drop = preset.run_length if lifetime is None else last + lifetime
        if len(spans[i]) < MOST_BUILDS:
            spans[i].append([first, last, min(drop, preset.run_length)])
    return spans


def timeline_counts(name: str) -> list[int]:
    """How many times each structure builds over the run."""
    preset = PRESETS[name]
    workload = Workload(Heap(Collector()), preset.workload)
    workload.run_to(preset.run_length)
    counts = [0] * len(preset.workload.structures)
    for i, _, _ in workload.builds:
        counts[i] += 1
    return counts


def main() -> None:
    out = {}
    for name, preset in PRESETS.items():
        spans = timeline(name)
        structures = []
        counts = timeline_counts(name)
        for i, structure in enumerate(preset.workload.structures):
            builds = counts[i]
            structures.append(
                {
                    "label": LABELS[name][i],
                    "shape": type(structure.shape).__name__,
                    "parameter": next(iter(vars(structure.shape).values()), None),
                    "size": structure.size,
                    "root": structure.root,
                    "lifetime": structure.lifetime,
                    "rebuild_interval": structure.rebuild_interval,
                    "build_churn": structure.build_churn,
                    "full_collections": structure.full_collections,
                    "builds": builds,
                    "spans": spans[i],
                    **sample(structure),
                }
            )
        churn = preset.workload.churn
        out[name] = {
            "run_length": preset.run_length,
            "churn": {
                "cycle_share": float(churn.cycle_share),
                "cycle_size": churn.cycle_size,
                "lifetime_mean": churn.lifetime_mean,
                "long_share": float(churn.long_share),
                "long_lifetimes": list(churn.long_lifetimes),
            },
            "structures": structures,
        }
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
