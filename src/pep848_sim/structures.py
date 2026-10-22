"""Structures: objects a workload builds in one shape, hangs off one root and drops
together.

A shape gives the links each new object gets, by its index among the structure's
objects; the root is object 0.
"""

from dataclasses import dataclass
from typing import Literal

from pep848_sim.heap import Heap

type Root = Literal["module", "frame"]


@dataclass(frozen=True)
class Chains:
    """Chains of module globals: the root, a module, holds `width` chains, and each
    new object goes on the end of the next chain in turn."""

    width: int

    def cyclic_garbage(self, size: int) -> int:
        """How many objects of a dropped structure of this size stay as cyclic
        garbage."""
        return 0

    def links(self, i: int) -> list[tuple[int, int]]:
        if not i:
            return []
        return [(max(i - self.width, 0), i)]


@dataclass(frozen=True)
class Tree:
    """A binary tree with parent pointers: object i and its parent link each other."""

    def cyclic_garbage(self, size: int) -> int:
        """How many objects of a dropped structure of this size stay as cyclic
        garbage: every object lies on a cycle with its parent, unless the root stands
        alone."""
        return size if size > 1 else 0

    def links(self, i: int) -> list[tuple[int, int]]:
        if not i:
            return []
        parent = (i - 1) // 2
        return [(parent, i), (i, parent)]


type Shape = Chains | Tree


@dataclass(frozen=True)
class StructureParameters:
    """The workload parameters of one structure. A long-lived structure has no
    lifetime and no rebuild interval."""

    shape: Shape
    size: int
    root: Root
    lifetime: int | None
    rebuild_interval: int | None
    # The churn allocations after each built object.
    build_churn: int

    def __post_init__(self) -> None:
        build = self.size * (1 + self.build_churn)
        if self.rebuild_interval is not None and build > self.rebuild_interval:
            raise ValueError(
                f"a {build} kB build outlasts its {self.rebuild_interval} kB interval"
            )


class Build:
    """One build of a structure over a heap, one object per kB in its shape's
    order."""

    def __init__(self, heap: Heap, parameters: StructureParameters) -> None:
        self._heap = heap
        self._parameters = parameters
        self._objects: list[int] = []

    @property
    def done(self) -> bool:
        return len(self._objects) == self._parameters.size

    def add(self) -> None:
        """Allocate the next object and link it in, then let go of its frame root.
        A frame-rooted structure's root keeps its frame root, and a module-rooted
        structure's root hangs off sys instead."""
        heap = self._heap
        objects = self._objects
        x = heap.allocate()
        objects.append(x)
        i = len(objects) - 1
        for source, target in self._parameters.shape.links(i):
            heap.link(objects[source], objects[target])
        if i:
            heap.let_go_frame_root(x)
        elif self._parameters.root == "module":
            heap.link(heap.module_root, x)
            heap.let_go_frame_root(x)

    def drop(self) -> None:
        """Let go of the structure's root. What lies on its shape's cycles stays as
        cyclic garbage, and refcounting frees the rest on the spot."""
        heap = self._heap
        root = self._objects[0]
        unreachable = self._parameters.shape.cyclic_garbage(len(self._objects))
        if self._parameters.root == "module":
            heap.unlink(heap.module_root, root, leaves_unreachable=unreachable)
        else:
            heap.let_go_frame_root(root, leaves_unreachable=unreachable)
