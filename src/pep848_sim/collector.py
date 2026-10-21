"""What both collectors share: the spaces they keep the heap's objects in.

The collector owns every space, the nursery included, as CPython's collector owns
its generation lists. The heap hands it each new object.
"""

from collections.abc import Iterator


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
        self._spaces: dict[int, Space] = {}

    def add(self, x: int) -> None:
        self.nursery._objects[x] = None
        self._spaces[x] = self.nursery

    def move(self, x: int, space: Space) -> None:
        del self._spaces[x]._objects[x]
        space._objects[x] = None
        self._spaces[x] = space

    def remove(self, x: int) -> None:
        del self._spaces.pop(x)._objects[x]
