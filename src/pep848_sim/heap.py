"""The heap both collectors run over: simulated objects, their references, the
roots that keep them reachable, and the allocation clock.

A simulated object is an int indexing the heap's list of records. Its references
are ints too, so the simulator makes no reference cycles of its own for the host's
collector to chase. The heap hands each new object to its collector, which owns
the spaces.
"""

from pep848_sim.collector import Collector


class SimulatedObject:
    """One object's state, kept in one place: what it holds and what holds it."""

    __slots__ = ("frame_roots", "reference_count", "references")

    def __init__(self, reference_count: int, frame_roots: int) -> None:
        self.references: list[int] = []
        # Every reference into the object: from other objects, its frame roots,
        # and for sys the interpreter's.
        self.reference_count = reference_count
        self.frame_roots = frame_roots


class Heap:
    def __init__(self, collector: Collector) -> None:
        self._collector = collector
        # A freed object's record is None.
        # sys exists before the run begins, so making it moves no clock, and the
        # interpreter holds it for good.
        self._objects: list[SimulatedObject | None] = [SimulatedObject(1, 0)]
        self._module_root = 0
        collector.add(self._module_root)
        self._clock = 0

    @property
    def clock(self) -> int:
        return self._clock

    @property
    def module_root(self) -> int:
        return self._module_root

    def frame_roots(self) -> dict[int, int]:
        return {
            x: record.frame_roots
            for x, record in enumerate(self._objects)
            if record is not None and record.frame_roots
        }

    def take_frame_root(self, x: int) -> None:
        record = self._alive(x)
        record.frame_roots += 1
        record.reference_count += 1

    def let_go_frame_root(self, x: int) -> None:
        record = self._objects[x]
        if record is None or not record.frame_roots:
            raise ValueError(f"no frame root on object {x}")
        record.frame_roots -= 1
        record.reference_count -= 1
        assert record.reference_count >= 0, f"object {x}'s count < 0"
        if not record.reference_count:
            self._free(x)

    def is_freed(self, x: int) -> bool:
        return self._objects[x] is None

    def allocate(self) -> int:
        """A new object, which its allocating frame holds, as in CPython."""
        x = len(self._objects)
        self._objects.append(SimulatedObject(1, 1))
        self._collector.add(x)
        self._clock += 1
        return x

    def allocate_unseen(self) -> None:
        self._clock += 1

    def link(self, source: int, target: int) -> None:
        held = self._alive(target)
        self._alive(source).references.append(target)
        held.reference_count += 1

    def references(self, x: int) -> tuple[int, ...]:
        record = self._objects[x]
        return () if record is None else tuple(record.references)

    def reference_count(self, x: int) -> int:
        record = self._objects[x]
        return 0 if record is None else record.reference_count

    def _alive(self, x: int) -> SimulatedObject:
        record = self._objects[x]
        if record is None:
            raise ValueError(f"object {x} is freed")
        return record

    def _free(self, x: int) -> None:
        """Free x by refcounting, and whatever that leaves at zero in turn."""
        stack = [x]
        while stack:
            y = stack.pop()
            record = self._alive(y)
            self._objects[y] = None
            self._collector.remove(y)
            for target in record.references:
                held = self._alive(target)
                held.reference_count -= 1
                assert held.reference_count >= 0, f"object {target}'s count < 0"
                if not held.reference_count:
                    stack.append(target)
