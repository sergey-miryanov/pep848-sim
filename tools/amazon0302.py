"""Write the links of the Amazon0302 shape from bm_networkx's own graph file,
amazon0302.txt.gz in pyperformance's data-files/benchmarks/bm_networkx/data.

networkx 3.4.2's read_adjlist reads each line "u v" in turn. A node it has not
seen makes its adjacency dict, then its attribute dict. An edge it has not seen
makes one data dict, which both endpoints' adjacency dicts hold. The shape's
objects past its head stand for one real object in 16 of that order (ADR 0002),
each for 16 of its own kind, and the table records what holds each: _adj, _node,
or, for an edge, the objects that stand for its endpoints' adjacency dicts.

The table is a zlib stream of unsigned LEB128 numbers, one or two for each
object: 0 for an adjacency dict, 1 for an attribute dict, or for an edge d + 1,
where d is how many objects back its nearer holder is, then how much farther
back its other holder is, or 0 when one object stands for both.
"""

import argparse
import gzip
import zlib
from bisect import bisect_right
from pathlib import Path

from pep848_sim.structures import AMAZON0302_HEAD, AMAZON0302_LINKS, AMAZON0302_SIZE

# The kinds of real object read_adjlist makes, besides an edge's data dict.
ADJACENCY, ATTRIBUTES = -1, -2


def real_objects(path: Path) -> list[tuple[int, ...]]:
    """Each real object in the order read_adjlist makes them: (ADJACENCY,),
    (ATTRIBUTES,), or an edge's endpoints' adjacency dicts, by their places."""
    made: dict[str, int] = {}
    edges: set[tuple[str, str]] = set()
    objects: list[tuple[int, ...]] = []
    with gzip.open(path, "rt") as lines:
        for line in lines:
            if line.startswith("#"):
                continue
            u, v = line.split()
            for node in (u, v):
                if node not in made:
                    made[node] = len(objects)
                    objects += [(ADJACENCY,), (ATTRIBUTES,)]
            edge = (u, v) if u < v else (v, u)
            if u != v and edge not in edges:
                edges.add(edge)
                objects.append((made[u], made[v]))
    return objects


def table(objects: list[tuple[int, ...]]) -> list[int]:
    """The numbers for the shape's objects past its head."""
    count = AMAZON0302_SIZE - AMAZON0302_HEAD

    def sampled(j: int) -> tuple[int, ...]:
        return objects[min(16 * (j - AMAZON0302_HEAD), len(objects) - 1)]

    places = range(AMAZON0302_HEAD, AMAZON0302_HEAD + count)
    adjacency = [j for j in places if sampled(j) == (ADJACENCY,)]

    def holder(real: int, j: int) -> int:
        """The last object before j standing for adjacency dicts, at or before
        the one that stands for real object `real`, or _adj itself."""
        k = bisect_right(adjacency, min(AMAZON0302_HEAD + real // 16, j - 1)) - 1
        return adjacency[k] if k >= 0 else AMAZON0302_HEAD - 1

    numbers: list[int] = []
    for j in places:
        kind = sampled(j)
        if kind == (ADJACENCY,):
            numbers.append(0)
        elif kind == (ATTRIBUTES,):
            numbers.append(1)
        else:
            backs = sorted({j - holder(real, j) for real in kind})
            numbers += [backs[0] + 1, backs[-1] - backs[0]]
    return numbers


def encode(numbers: list[int]) -> bytes:
    out = bytearray()
    for n in numbers:
        while n >= 0x80:
            out.append(n & 0x7F | 0x80)
            n >>= 7
        out.append(n)
    return zlib.compress(bytes(out), 9)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("graph", type=Path, help="amazon0302.txt.gz")
    path = parser.parse_args().graph
    AMAZON0302_LINKS.write_bytes(encode(table(real_objects(path))))


if __name__ == "__main__":
    main()
