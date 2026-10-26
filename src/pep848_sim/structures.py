"""Structures: objects a workload builds in one shape, hangs off one root and drops
together.

A shape gives the links each new object gets, by its index among the structure's
objects; the root is object 0.
"""

import traceback
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from types import FunctionType
from typing import Any, Literal, get_args

from pep848_sim.collectors.heap import Heap

type Root = Literal["module", "frame"]

# The file name an own shape's code runs under, which finds its lines in a
# traceback.
_OWN_FILE = "<your shape>"
# How many of an own shape's first objects a check calls links(i) on.
_CHECKED = 1024


@dataclass(frozen=True)
class Chains:
    """Chains of module globals: the root, a module, holds `width` chains, and each
    new object goes on the end of the next chain in turn."""

    width: int

    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError(f"{self.width} chains hold no objects")

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


@dataclass(frozen=True)
class Hierarchy:
    """A tree whose objects hold their children and nothing links back up, as an
    ElementTree holds its elements or a TaskGroup its tasks. Each object holds up to
    `branches` children, and the objects come a level at a time, as `Tree`'s do."""

    branches: int

    def __post_init__(self) -> None:
        if self.branches < 1:
            raise ValueError(
                f"a hierarchy of {self.branches} branches ends at its root"
            )

    def cyclic_garbage(self, size: int) -> int:
        """How many objects of a dropped structure of this size stay as cyclic
        garbage."""
        return 0

    def links(self, i: int) -> list[tuple[int, int]]:
        if not i:
            return []
        return [((i - 1) // self.branches, i)]


@dataclass(frozen=True)
class Rings:
    """Rings in a list, as create_gc_cycles builds them: the root, a list, holds
    each ring's first object, and each object links to the next in its ring and
    back. A ring closes as its last object, `length` objects in, links back to its
    first."""

    length: int

    def __post_init__(self) -> None:
        if self.length < 1:
            raise ValueError(f"a ring of {self.length} objects holds none")

    def cyclic_garbage(self, size: int) -> int:
        """How many objects of a dropped structure of this size stay as cyclic
        garbage: every object of a ring, closed or not, that links both ways with a
        neighbour or with itself. The list goes on the spot, and so does a last ring
        cut short at its first object."""
        objects = max(size - 1, 0)
        lone = objects % self.length == 1
        return objects - lone

    def links(self, i: int) -> list[tuple[int, int]]:
        if not i:
            return []
        first = i - (i - 1) % self.length
        links = [(0, i)] if i == first else [(i - 1, i), (i, i - 1)]
        if i - first == self.length - 1:
            links += [(i, first), (first, i)]
        return links


@dataclass(frozen=True)
class Graph:
    """A networkx graph in a module's globals, as connected_components loads it. The
    root, the globals, lies on a cycle with a function that reads them, as each
    function's __globals__ makes one. The root holds each node, and each node holds
    the data of its `edges` edges to the nodes read just before it, which it shares
    with them. Nothing in the graph links back, so only the root's cycle keeps it:
    once its module goes, all of it stays as cyclic garbage."""

    edges: int

    def __post_init__(self) -> None:
        if self.edges < 0:
            raise ValueError(f"a node cannot bring {self.edges} edges")

    def cyclic_garbage(self, size: int) -> int:
        """How many objects of a dropped structure of this size stay as cyclic
        garbage: all of them, held by the root's cycle, unless the root stands
        alone."""
        return size if size > 1 else 0

    def links(self, i: int) -> list[tuple[int, int]]:
        if not i:
            return []
        if i == 1:
            return [(0, 1), (1, 0)]
        span = self.edges + 1
        node, edge = divmod(i - 2, span)
        if not edge:
            return [(0, i)]
        holder = 2 + node * span
        links = [(holder, i)]
        if edge <= node:
            links.append((holder - edge * span, i))
        return links


@dataclass(frozen=True)
class Own:
    """A shape of the reader's own, from Python code that defines `links(i)`, or
    one function by another name: the links object i brings, as (source, target)
    pairs among objects 0 to i. One of them, from an earlier object, holds object
    i, or it would be garbage as soon as it is built. The simulator calls links(i)
    more than once for an object, so its answer depends on i alone."""

    code: str
    # The line of the reader's text the code starts on, which messages count
    # from: the box's first, or the function's own in a workload source.
    line: int = field(default=1, compare=False)
    # The function the code defines for its links, which messages name.
    _name: str = field(init=False, repr=False, compare=False)
    _links: Callable[[int], Any] = field(init=False, repr=False, compare=False)
    # The cyclic garbage a drop leaves, by the structure's size.
    _garbage: dict[int, int] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        try:
            compiled = compile("\n" * (self.line - 1) + self.code, _OWN_FILE, "exec")
        except SyntaxError as error:
            raise ValueError(
                f"line {error.lineno} of your shape: {error.msg}"
            ) from None
        namespace: dict[str, object] = {}
        try:
            exec(compiled, namespace)
        except Exception as error:
            raise ValueError(_raised(error)) from None
        name = "links" if callable(namespace.get("links")) else _alone(namespace)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_links", namespace[name])

    def cyclic_garbage(self, size: int) -> int:
        """How many objects of a dropped structure of this size stay as cyclic
        garbage: those its links leave alive once refcounting has freed all it
        can."""
        if size not in self._garbage:
            out: dict[int, list[int]] = defaultdict(list)
            count = [0] * size
            for i in range(size):
                for source, target in self.links(i):
                    out[source].append(target)
                    count[target] += 1
            # An earlier object holds each object but the first, and the drop takes
            # away the first's own holder.
            freed = [x for x in range(size) if not count[x]]
            alive = size - len(freed)
            while freed:
                for target in out[freed.pop()]:
                    count[target] -= 1
                    if not count[target]:
                        freed.append(target)
                        alive -= 1
            self._garbage[size] = alive
        return self._garbage[size]

    def links(self, i: int) -> list[tuple[int, int]]:
        call = f"{self._name}({i})"
        try:
            made = self._links(i)
        except Exception as error:
            raise ValueError(_raised(error, call)) from None
        try:
            pairs = [(source, target) for source, target in made]
        except TypeError, ValueError:
            raise ValueError(
                f"{call} gives {made!r}, not (source, target) pairs"
            ) from None
        for pair in pairs:
            if not all(type(x) is int and 0 <= x <= i for x in pair):
                raise ValueError(
                    f"{call} gives {pair!r}: a link joins two of objects 0 to {i}"
                )
        if i and not any(source < target == i for source, target in pairs):
            raise ValueError(
                f"{call} gives object {i} no holder among objects 0 to {i - 1},"
                " so it would be garbage as soon as it is built"
            )
        return pairs

    def check(self, size: int) -> None:
        """Call links(i) twice on each of the first objects of a structure of this
        size, so that a link the heap cannot make, or an answer that changes from
        one call to the next, shows before a run starts."""
        for i in range(min(size, _CHECKED)):
            if self.links(i) != self.links(i):
                raise ValueError(
                    f"{self._name}({i}) gave two answers, where it must depend on i"
                    " alone"
                )


def _alone(namespace: dict[str, object]) -> str:
    """The one function an own shape's code defines, which gives its links when it
    defines no links(i)."""
    defined = [
        name
        for name, value in namespace.items()
        if isinstance(value, FunctionType) and value.__code__.co_filename == _OWN_FILE
    ]
    if len(defined) != 1:
        raise ValueError("your shape defines no links(i)")
    return defined[0]


def _raised(error: Exception, call: str = "") -> str:
    """What the reader's code raised, in a call of its links or as it ran, and the
    line of their text it raised at."""
    lines = [
        frame.lineno
        for frame in traceback.extract_tb(error.__traceback__)
        if frame.filename == _OWN_FILE
    ]
    name = type(error).__name__
    if not call:
        return f"your shape raised {name} at line {lines[-1]}: {error}"
    where = f" at line {lines[-1]}" if lines else ""
    return f"{call} raised {name}{where}: {error}"


type Shape = Chains | Tree | Hierarchy | Graph | Rings | Own


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
    # Whether the workload calls `gc.collect()` before each build and after each
    # drop, as create_gc_cycles does.
    full_collections: bool = False
    # Whether a frame holds a structure sys holds while it builds, as a module-level
    # `X = build()` holds what build() makes until it returns: sys takes it once the
    # build ends, its churn included.
    built_in_frame: bool = False

    def __post_init__(self) -> None:
        if self.root not in get_args(Root.__value__):
            raise ValueError(f"no root {self.root!r}")
        if self.size < 1:
            raise ValueError(f"a structure of {self.size} objects builds nothing")
        if self.built_in_frame and self.root == "frame":
            raise ValueError("a structure a frame holds is built in one already")
        if self.lifetime is not None and self.lifetime < 0:
            raise ValueError(f"a structure cannot live {self.lifetime} kB")
        if self.build_churn < 0:
            raise ValueError(
                f"a build cannot follow each object with {self.build_churn} churn"
                " allocations"
            )
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
        structure's root hangs off sys instead, unless it is built in a frame."""
        heap = self._heap
        objects = self._objects
        x = heap.allocate()
        objects.append(x)
        i = len(objects) - 1
        for source, target in self._parameters.shape.links(i):
            heap.link(objects[source], objects[target])
        if i:
            heap.let_go_frame_root(x)
        elif self._parameters.root == "module" and not self._parameters.built_in_frame:
            self._hang_off_sys()

    def finish(self) -> None:
        """The build has ended: sys takes a structure built in a frame."""
        if self._parameters.built_in_frame:
            self._hang_off_sys()

    def _hang_off_sys(self) -> None:
        heap = self._heap
        root = self._objects[0]
        heap.link(heap.module_root, root)
        heap.let_go_frame_root(root)

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
