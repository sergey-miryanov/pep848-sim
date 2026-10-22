"""What both collectors share: their settings, the spaces they keep the heap's
objects in, and how they find and free the cyclic garbage among the objects a
collection examines.

The collector owns every space, the nursery included, as CPython's collector owns
its generation lists. The heap hands it each new object, and calls for a
collection at each multiple of threshold0.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

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


class Space:
    """Objects in the order they entered."""

    def __init__(self) -> None:
        self._objects: dict[int, None] = {}

    def __iter__(self) -> Iterator[int]:
        return iter(self._objects)


class Collector:
    def __init__(self, settings: CollectorSettings | None = None) -> None:
        self.settings = CollectorSettings() if settings is None else settings
        self.nursery = Space()
        # Each object's space, as CPython's PyGC_Head links an object into a list.
        # Only _place changes it, together with the spaces themselves.
        self._spaces: dict[int, Space] = {}

    def attach(self, heap: Heap) -> None:
        """Take the heap to collect, which hands itself over as it starts."""
        self._heap = heap

    def collect(self) -> None:
        """Run one collection. The base collects nothing; each collector says how
        it collects."""

    def collect_cycles(self, objects: Iterable[int]) -> list[int]:
        """Free the cyclic garbage among `objects` and return the survivors in their
        order, as the pseudocode's collect_cycles does."""
        examined = list(objects)
        garbage = find_unreachable(self._heap, examined)
        self._heap.free_cyclic_garbage(garbage)
        freed = set(garbage)
        return [x for x in examined if x not in freed]

    def add(self, x: int) -> None:
        self._place(x, self.nursery)

    def move(self, x: int, space: Space) -> None:
        self._place(x, space)

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
