"""What both collectors share: their settings, the spaces they keep the heap's
objects in, and how they find and free the cyclic garbage among the objects a
collection examines.

The collector owns every space, the nursery included, as CPython's collector owns
its generation lists. The heap hands it each new object, and calls for a
collection at each multiple of threshold0.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, NamedTuple

if TYPE_CHECKING:
    from pep848_sim.heap import Heap


@dataclass(frozen=True)
class CollectorSettings:
    """The three thresholds of one `gc.set_threshold()` call, which both collectors
    share and each reads its own way. The defaults are the PEP's."""

    # kB allocated between collections: both collectors collect at its multiples.
    threshold0: int = 2000
    threshold1: int = 10
    threshold2: int = 10


@dataclass(frozen=True)
class CollectionCounts:
    """What one collection did: its kind, and how many objects it marked, saw
    survive and freed."""

    kind: str
    marked: int
    survived: int
    freed: int

    @property
    def work(self) -> int:
        """The simulator's stand-in for the collection's pause."""
        return self.marked + self.survived + self.freed


class Record(NamedTuple):
    """What one collection did and the heap around it, in ints and strings
    (ADR 0007). The heap appears before the collection and after it (ADR 0010):
    by space, in the order the collector's SPACES name them, and its reachable
    part. The rest of each is uncollected garbage."""

    clock: int
    kind: str
    marked: int
    survived: int
    freed: int
    # The work budget after the collection, and the sweeps ended by then. The
    # legacy collector keeps no budget and runs no sweeps, and reports 0 for both.
    work_to_do: int
    sweep: int
    spaces_before: tuple[int, ...]
    spaces_after: tuple[int, ...]
    reachable_before: int
    reachable_after: int


class Space:
    """Objects in the order they entered, held as the pseudocode's lists hold them.
    Each change goes through the collector, which keeps every object in one space."""

    def __init__(self, collector: Collector) -> None:
        self._collector = collector
        self._objects: dict[int, None] = {}

    def __iter__(self) -> Iterator[int]:
        return iter(self._objects)

    def __len__(self) -> int:
        return len(self._objects)

    def __contains__(self, x: object) -> bool:
        return x in self._objects

    def append(self, x: int) -> None:
        """Put x last, taking it out of the space it was in."""
        self._collector._place(x, self)

    def extend(self, objects: Iterable[int]) -> None:
        # A copy first, so that another space can move here whole.
        for x in list(objects):
            self.append(x)

    def pop(self, index: Literal[0, -1] = -1) -> int:
        """Take out the first object or the last, and return it."""
        x = next(iter(self._objects) if index == 0 else reversed(self._objects))
        self._collector._place(x, None)
        return x

    def remove(self, x: int) -> None:
        assert x in self._objects, f"object {x} is not in the space"
        self._collector._place(x, None)


class Collector:
    # The spaces a record reports, in the order a stacked chart draws them.
    SPACES: ClassVar[tuple[str, ...]] = ("nursery",)

    def __init__(self, settings: CollectorSettings | None = None) -> None:
        self.settings = CollectorSettings() if settings is None else settings
        self.counts: list[CollectionCounts] = []
        self.records: list[Record] = []
        self.nursery = Space(self)
        # Each object's space, as CPython's PyGC_Head links an object into a list.
        # Only _place changes it, together with the spaces themselves.
        self._spaces: dict[int, Space] = {}

    def attach(self, heap: Heap) -> None:
        """Take the heap to collect, which hands itself over as it starts."""
        self._heap = heap

    def collect_at_boundary(self) -> None:
        """Run one collection, as the heap asks at each multiple of threshold0, and
        record it with the heap before and after it."""
        heap = self._heap
        counted = len(self.counts)
        spaces_before = self.space_sizes()
        reachable_before = len(heap) - heap.uncollected_garbage
        self.collect()
        if len(self.counts) == counted:
            return  # the base collects nothing, so it has nothing to record
        counts = self.counts[-1]
        self.records.append(
            Record(
                heap.clock,
                counts.kind,
                counts.marked,
                counts.survived,
                counts.freed,
                self.budget(),
                self.sweep(),
                spaces_before,
                self.space_sizes(),
                reachable_before,
                len(heap) - heap.uncollected_garbage,
            )
        )

    def collect(self) -> None:
        """Run one collection. The base collects nothing; each collector says how
        it collects."""

    def space_sizes(self) -> tuple[int, ...]:
        """The objects in each space SPACES names."""
        return (len(self.nursery),)

    def budget(self) -> int:
        return 0

    def sweep(self) -> int:
        return 0

    def collect_cycles(self, objects: Iterable[int]) -> list[int]:
        """Free the cyclic garbage among `objects` and return the survivors in their
        order, as the pseudocode's collect_cycles does."""
        heap = self._heap
        examined = list(objects)
        garbage = find_unreachable(heap, examined)
        # As delete_garbage does: clear each object, and refcounting frees the rest.
        # A clear can free objects later in the list, so skip those.
        for x in garbage:
            if not heap.is_freed(x):
                heap.clear(x)
        freed = set(garbage)
        return [x for x in examined if x not in freed]

    def add(self, x: int) -> None:
        self.nursery.append(x)

    def add_module_root(self, x: int) -> None:
        """Take sys, which the heap makes before the run begins."""
        self.add(x)

    def remove(self, x: int) -> None:
        self._place(x, None)

    def _place(self, x: int, space: Space | None) -> None:
        """Take x out of its space, if it has one, and put it last in `space`."""
        old = self._spaces.pop(x, None)
        if old is not None:
            del old._objects[x]
        if space is not None:
            space._objects[x] = None
            self._spaces[x] = space


def find_unreachable(heap: Heap, examined: Iterable[int]) -> list[int]:
    """The objects among `examined` that nothing outside them reaches, in their
    order, found as CPython's collector finds them."""
    # Each object's references from outside the examined ones: its count less the
    # references from examined objects, as update_refs and subtract_refs leave it.
    from_outside = {x: heap.reference_count(x) for x in examined}
    for x in from_outside:
        for target in heap.references(x):
            if target in from_outside:
                from_outside[target] -= 1
    # What something outside holds survives, with all it reaches among the
    # examined objects, as in move_unreachable.
    stack = [x for x, held in from_outside.items() if held]
    reached = set(stack)
    while stack:
        for target in heap.references(stack.pop()):
            if target in from_outside and target not in reached:
                reached.add(target)
                stack.append(target)
    return [x for x in from_outside if x not in reached]
