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
        self._freed: list[bool] = [False]
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
        if not self._reference_counts[x]:
            self._free(x)

    def is_freed(self, x: int) -> bool:
        return self._freed[x]

    def _free(self, x: int) -> None:
        """Free x by refcounting, and whatever that leaves at zero in turn."""
        counts = self._reference_counts
        stack = [x]
        while stack:
            y = stack.pop()
            self._collector.remove(y)
            self._freed[y] = True
            for target in self._references[y]:
                counts[target] -= 1
                if not counts[target]:
                    stack.append(target)
            self._references[y] = []

    def allocate(self) -> int:
        """A new object, which its allocating frame holds, as in CPython."""
        x = len(self._references)
        self._references.append([])
        self._reference_counts.append(1)
        self._frame_roots[x] = 1
        self._freed.append(False)
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
