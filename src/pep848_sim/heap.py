"""The heap both collectors run over: simulated objects, their references, the
roots that keep them reachable, the allocation clock, and a count of uncollected
garbage.

A simulated object is an int indexing the heap's list of records. Its references
are ints too, so the simulator makes no reference cycles of its own for the host's
collector to chase. The heap hands each new object to its collector, which owns
the spaces.

A walk at every collection would take longer than most collections, so the heap
keeps the count as it changes: the workload says how many objects each let-go
leaves unreachable, and freeing a group that a collection found takes it off.
"""

from collections import Counter
from collections.abc import Iterable

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
        self._alive_count = 1
        self._uncollected_garbage = 0
        self._module_root = 0
        collector.add(self._module_root)
        self._clock = 0

    def __len__(self) -> int:
        """The alive objects, sys among them."""
        return self._alive_count

    @property
    def clock(self) -> int:
        return self._clock

    @property
    def uncollected_garbage(self) -> int:
        return self._uncollected_garbage

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

    def let_go_frame_root(self, x: int, leaves_unreachable: int = 0) -> None:
        """Let go of one frame root on x, which leaves `leaves_unreachable` objects
        unreachable, as the workload knows from building them."""
        record = self._objects[x]
        if record is None or not record.frame_roots:
            raise ValueError(f"no frame root on object {x}")
        record.frame_roots -= 1
        self._let_go([x])
        self._count_garbage(leaves_unreachable)

    def free_cyclic_garbage(self, group: Iterable[int]) -> None:
        """Free a group of cyclic garbage that a collection found, then let go of its
        references to objects outside it, which frees what only the group held."""
        # Each member once, in the group's order (ADR 0007): a member listed twice
        # would count its references twice.
        members = {x: self._alive(x) for x in group}
        held_inside = Counter(t for m in members.values() for t in m.references)
        for x, record in members.items():
            if record.reference_count > held_inside[x]:
                raise ValueError(f"something outside the group holds object {x}")
        alive_before = self._alive_count
        for x in members:
            self._release(x)
        self._let_go(
            t for m in members.values() for t in m.references if t not in members
        )
        self._count_garbage(self._alive_count - alive_before)

    def is_freed(self, x: int) -> bool:
        return self._objects[x] is None

    def allocate(self) -> int:
        """A new object, which its allocating frame holds, as in CPython."""
        x = len(self._objects)
        self._objects.append(SimulatedObject(1, 1))
        self._alive_count += 1
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

    def _count_garbage(self, change: int) -> None:
        self._uncollected_garbage += change
        # sys stays reachable, so at least one alive object is not garbage.
        assert 0 <= self._uncollected_garbage < self._alive_count, (
            f"{self._uncollected_garbage} of {self._alive_count} objects uncollected"
        )

    def _let_go(self, targets: Iterable[int]) -> None:
        """Let go of one reference to each target, and free by refcounting whatever
        that leaves at zero, in turn."""
        stack = list(targets)
        while stack:
            x = stack.pop()
            record = self._alive(x)
            record.reference_count -= 1
            assert record.reference_count >= 0, f"object {x}'s count < 0"
            if not record.reference_count:
                self._release(x)
                stack.extend(record.references)

    def _release(self, x: int) -> None:
        self._objects[x] = None
        self._alive_count -= 1
        self._collector.remove(x)
