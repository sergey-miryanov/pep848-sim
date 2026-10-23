"""What both collectors share: their settings, the spaces they keep the heap's
objects in, how they find and free the cyclic garbage among the objects a
collection examines, and the record each collection leaves.

The collector owns every space, the nursery included, as CPython's collector owns
its generation lists. The heap hands it each new object, and calls for a
collection at each multiple of threshold0.
"""

from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, NamedTuple

if TYPE_CHECKING:
    from pep848_sim.collectors.heap import Heap


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
    An object sits in one space at a time, as CPython's PyGC_Head links it into one
    list: putting it in a space takes it out of the one it was in."""

    def __init__(self, collector: Collector) -> None:
        # The collector's map from each object to its space, which its spaces share.
        self._space_of = collector.space_of
        self._objects: dict[int, None] = {}

    def __iter__(self) -> Iterator[int]:
        return iter(self._objects)

    def __len__(self) -> int:
        return len(self._objects)

    def __contains__(self, x: object) -> bool:
        return x in self._objects

    def append(self, x: int) -> None:
        """Put x last, taking it out of the space it was in."""
        self._take_out(x)
        self._objects[x] = None
        self._space_of[x] = self

    def extend(self, objects: Iterable[int]) -> None:
        # A copy first, so that another space can move here whole.
        for x in list(objects):
            self.append(x)

    def pop(self, index: Literal[0, -1] = -1) -> int:
        """Take out the first object or the last, and return it."""
        x = next(iter(self._objects) if index == 0 else reversed(self._objects))
        self._take_out(x)
        return x

    def remove(self, x: int) -> None:
        assert x in self._objects, f"object {x} is not in the space"
        self._take_out(x)

    def _take_out(self, x: int) -> None:
        """Take x out of its space, this one or another, if it has one."""
        space = self._space_of.pop(x, None)
        if space is not None:
            del space._objects[x]


class Collector:
    """The base both collectors build on. It counts each collection as it runs:
    collect_cycles adds the objects it saw survive and those it freed, an old
    collection adds those it marked, and recording() turns what one collection
    added into its counts and its record."""

    # The spaces a record reports, young to old.
    SPACES: ClassVar[tuple[str, ...]] = ("nursery",)

    def __init__(self, settings: CollectorSettings | None = None) -> None:
        self.settings = CollectorSettings() if settings is None else settings
        self.counts: list[CollectionCounts] = []
        self.records: list[Record] = []
        # Each object's space, as CPython's PyGC_Head links an object into a list.
        # Only the spaces write it, as they take objects in and out.
        self.space_of: dict[int, Space] = {}
        self.nursery = Space(self)
        # How many objects the collections so far marked, saw survive and freed.
        self.marked = 0
        self.survived = 0
        self.freed = 0

    def attach(self, heap: Heap) -> None:
        """Take the heap to collect, which hands itself over as it starts."""
        self._heap = heap

    def collect(self) -> None:
        """Run one collection, as the heap asks at each multiple of threshold0. The
        base collects nothing; each collector says how it collects, and records the
        collection with `recording()`."""

    @contextmanager
    def recording(self, kind: str) -> Generator[None]:
        """Count and record the collection run inside, with the heap before and
        after it."""
        heap = self._heap
        spaces_before = self.space_sizes()
        reachable_before = len(heap) - heap.uncollected_garbage
        marked, survived, freed = self.marked, self.survived, self.freed
        yield
        counts = CollectionCounts(
            kind,
            self.marked - marked,
            self.survived - survived,
            self.freed - freed,
        )
        self.counts.append(counts)
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

    def space_sizes(self) -> tuple[int, ...]:
        """The objects in each space SPACES names. The base reports the nursery, and
        each collector adds the spaces it makes."""
        return (len(self.nursery),)

    def budget(self) -> int:
        return 0

    def sweep(self) -> int:
        return 0

    def collect_cycles(self, objects: Iterable[int]) -> list[int]:
        """Free the cyclic garbage among `objects` and return the survivors in their
        order, as the pseudocode's collect_cycles does, counting both."""
        heap = self._heap
        examined = list(objects)
        garbage = find_unreachable(heap, examined)
        # As delete_garbage does: clear each object, and refcounting frees the rest.
        # A clear can free objects later in the list, so skip those.
        for x in garbage:
            if not heap.is_freed(x):
                heap.clear(x)
        freed = set(garbage)
        survivors = [x for x in examined if x not in freed]
        self.survived += len(survivors)
        self.freed += len(freed)
        return survivors

    def add(self, x: int) -> None:
        self.nursery.append(x)

    def add_module_root(self, x: int) -> None:
        """Take sys, which the heap makes before the run begins."""
        self.add(x)

    def remove(self, x: int) -> None:
        """Take x out of its space, as the heap asks when it frees x."""
        self.space_of[x].remove(x)


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
