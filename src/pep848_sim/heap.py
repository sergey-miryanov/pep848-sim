"""The heap both collectors run over: simulated objects, their references, the
roots that keep them reachable, and the allocation clock.

A simulated object is an int indexing the heap's lists, so the simulator makes no
reference cycles of its own for the host's collector to chase. The heap hands each
new object to its collector, which owns the spaces.
"""

from pep848_sim.collector import Collector


class Heap:
    def __init__(self, collector: Collector) -> None:
        self._collector = collector
        # sys exists before the run begins, so making it moves no clock, and the
        # interpreter holds it for good.
        self._references: list[list[int]] = [[]]
        self._reference_counts: list[int] = [1]
        self._module_root = 0
        collector.add(self._module_root)
        self._frame_roots: dict[int, int] = {}
        self._clock = 0

    @property
    def clock(self) -> int:
        return self._clock

    @property
    def module_root(self) -> int:
        return self._module_root

    def frame_roots(self) -> dict[int, int]:
        return dict(self._frame_roots)

    def take_frame_root(self, x: int) -> None:
        self._frame_roots[x] = self._frame_roots.get(x, 0) + 1
        self._reference_counts[x] += 1

    def let_go_frame_root(self, x: int) -> None:
        roots = self._frame_roots.get(x, 0)
        if not roots:
            raise ValueError(f"no frame root on object {x}")
        if roots == 1:
            del self._frame_roots[x]
        else:
            self._frame_roots[x] = roots - 1
        self._reference_counts[x] -= 1

    def allocate(self) -> int:
        x = len(self._references)
        self._references.append([])
        self._reference_counts.append(0)
        self._collector.add(x)
        self._clock += 1
        return x

    def allocate_unseen(self) -> None:
        self._clock += 1

    def link(self, source: int, target: int) -> None:
        self._references[source].append(target)
        self._reference_counts[target] += 1

    def references(self, x: int) -> tuple[int, ...]:
        return tuple(self._references[x])

    def reference_count(self, x: int) -> int:
        return self._reference_counts[x]
