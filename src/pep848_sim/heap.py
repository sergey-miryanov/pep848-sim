"""The heap both collectors run over: simulated objects, their references, and the
allocation clock.

A simulated object is an int indexing the heap's lists, so the simulator makes no
reference cycles of its own for the host's collector to chase.
"""


class Heap:
    def __init__(self) -> None:
        self._references: list[list[int]] = []
        self._reference_counts: list[int] = []
        self._clock = 0

    @property
    def clock(self) -> int:
        return self._clock

    def allocate(self) -> int:
        x = len(self._references)
        self._references.append([])
        self._reference_counts.append(0)
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
