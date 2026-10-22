"""The heap both collectors run over: simulated objects, their references, the
roots that keep them reachable, the allocation clock, and a count of uncollected
garbage.

A simulated object is an int, the key to its record among the heap's alive
objects. Its references are ints too, so the simulator makes no reference cycles
of its own for the host's collector to chase. The heap hands each new object to
its collector, which owns the spaces.

A walk at every collection would take longer than most collections, so the heap
keeps the count as it changes: the workload says how many objects each let-go
leaves unreachable, and what a collection's clears free comes off.
"""

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
        # The alive objects' records. A counter hands out the ints in allocation
        # order, no int serves twice, and freeing an object deletes its record.
        # sys exists before the run begins, so making it moves no clock, and the
        # interpreter holds it for good.
        self._objects = {0: SimulatedObject(1, 0)}
        self._next_object = 1
        self._uncollected_garbage = 0
        self._module_root = 0
        collector.attach(self)
        collector.add_module_root(self._module_root)
        self._clock = 0

    def __len__(self) -> int:
        """The alive objects, sys among them."""
        return len(self._objects)

    @property
    def clock(self) -> int:
        return self._clock

    @property
    def threshold0(self) -> int:
        """The kB between collections, a setting of the heap's collector."""
        return self._collector.settings.threshold0

    @property
    def uncollected_garbage(self) -> int:
        return self._uncollected_garbage

    @property
    def module_root(self) -> int:
        return self._module_root

    def frame_roots(self) -> dict[int, int]:
        return {
            x: record.frame_roots
            for x, record in self._objects.items()
            if record.frame_roots
        }

    def take_frame_root(self, x: int) -> None:
        record = self._alive(x)
        record.frame_roots += 1
        record.reference_count += 1

    def let_go_frame_root(self, x: int, leaves_unreachable: int = 0) -> None:
        """Let go of one frame root on x, which leaves `leaves_unreachable` objects
        unreachable, as the workload knows from building them."""
        record = self._objects.get(x)
        if record is None or not record.frame_roots:
            raise ValueError(f"no frame root on object {x}")
        record.frame_roots -= 1
        self._let_go([x])
        self._count_garbage(leaves_unreachable)

    def clear(self, x: int) -> None:
        """Let go of every reference x holds, as CPython's tp_clear does, and free
        by refcounting what that leaves at zero, x too once nothing holds it. Only a
        collection clears, and only objects it found unreachable, so whatever a
        clear frees comes off the uncollected garbage count."""
        record = self._alive(x)
        references = record.references
        record.references = []
        alive_before = len(self._objects)
        self._let_go(references)
        self._count_garbage(len(self._objects) - alive_before)

    def is_freed(self, x: int) -> bool:
        return x not in self._objects

    def allocate(self) -> int:
        """A new object, which its allocating frame holds, as in CPython."""
        self._collect_at_boundary()
        x = self._next_object
        self._next_object += 1
        self._objects[x] = SimulatedObject(1, 1)
        self._collector.add(x)
        self._clock += 1
        return x

    def allocate_unseen(self) -> None:
        self._collect_at_boundary()
        self._clock += 1

    def link(self, source: int, target: int) -> None:
        held = self._alive(target)
        self._alive(source).references.append(target)
        held.reference_count += 1

    def unlink(self, source: int, target: int, leaves_unreachable: int = 0) -> None:
        """Take away source's first reference to target, as a program does when it
        rebinds a global or removes an item from a container. The cut leaves
        `leaves_unreachable` objects unreachable, as the workload knows from building
        them."""
        references = self._alive(source).references
        if target not in references:
            raise ValueError(f"object {source} holds no reference to object {target}")
        references.remove(target)
        self._let_go([target])
        self._count_garbage(leaves_unreachable)

    def references(self, x: int) -> tuple[int, ...]:
        record = self._objects.get(x)
        return () if record is None else tuple(record.references)

    def reference_count(self, x: int) -> int:
        record = self._objects.get(x)
        return 0 if record is None else record.reference_count

    def _collect_at_boundary(self) -> None:
        """Collect if the clock sits on a multiple of threshold0, the start aside.
        Coming at the start of an allocation, the collection follows the let-gos of
        the kB that just ended (ADR 0005)."""
        if self._clock and not self._clock % self.threshold0:
            self._collector.collect_at_boundary()

    def _alive(self, x: int) -> SimulatedObject:
        record = self._objects.get(x)
        if record is None:
            raise ValueError(f"object {x} is freed")
        return record

    def _count_garbage(self, change: int) -> None:
        self._uncollected_garbage += change
        # sys stays reachable, so at least one alive object is not garbage.
        assert 0 <= self._uncollected_garbage < len(self._objects), (
            f"{self._uncollected_garbage} of {len(self._objects)} objects uncollected"
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
                del self._objects[x]
                self._collector.remove(x)
                stack.extend(record.references)
