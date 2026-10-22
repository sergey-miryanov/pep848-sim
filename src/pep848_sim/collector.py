"""What both collectors share: the spaces they keep the heap's objects in, and how
they find the unreachable objects among those a collection examines.

The collector owns every space, the nursery included, as CPython's collector owns
its generation lists. The heap hands it each new object.
"""

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pep848_sim.heap import Heap


class Space:
    """Objects in the order they entered."""

    def __init__(self) -> None:
        self._objects: dict[int, None] = {}

    def __iter__(self) -> Iterator[int]:
        return iter(self._objects)


class Collector:
    def __init__(self) -> None:
        self.nursery = Space()
        # Each object's space, as CPython's PyGC_Head links an object into a list.
        # Only _place changes it, together with the spaces themselves.
        self._spaces: dict[int, Space] = {}

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
