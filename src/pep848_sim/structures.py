"""Structures: objects a workload builds in one shape, hangs off one root and drops
together.

A shape gives the links each new object gets, by its index among the structure's
objects; the root is object 0.
"""

import math
import traceback
import zlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from functools import cache
from pathlib import Path
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
    the data of its `edges` edges, each of which it shares with a node read
    anywhere before it, as a file of edges names its nodes in no order. Nothing in
    the graph links back, so only the root's cycle keeps it: once its module goes,
    all of it stays as cyclic garbage."""

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
        if node:
            links.append((2 + _scramble(i) % node * span, i))
        return links


# Amazon0302's objects before the file's own: G, G.graph, G._node, G.__dict__,
# G.__networkx_cache__ and G._adj, in the order networkx makes them.
AMAZON0302_HEAD = 6
# The graph's simulated objects: read_adjlist's 1,424,118 real ones (ADR 0002).
AMAZON0302_SIZE = 1_424_118 // 16
# What holds each object past the head, as tools/amazon0302.py writes it.
AMAZON0302_LINKS = Path(__file__).with_name("amazon0302.links")


@dataclass(frozen=True)
class Amazon0302:
    """The Amazon co-purchasing graph as networkx 3.4.2's read_adjlist builds it
    from bm_networkx's amazon0302.txt.gz. G holds G.graph and G._node until setting
    G._node makes G.__dict__, which takes both over and then holds the cache and
    G._adj. Past those six, each object stands for one real object in 16 of the
    file's, in the order read_adjlist makes them: an adjacency dict, which _adj
    holds; an attribute dict, which _node holds; or an edge's data dict, which its
    endpoints' adjacency dicts hold. Nothing links back, so a dropped graph leaves
    no cyclic garbage. A larger structure repeats the file's pattern."""

    def cyclic_garbage(self, size: int) -> int:
        return 0

    def links(self, i: int) -> list[tuple[int, int]]:
        if not i:
            return []
        if i < 3:
            return [(0, i)]
        if i == 3:
            return [(0, 3), (3, 1), (3, 2)]
        if i < AMAZON0302_HEAD:
            return [(3, i)]
        table = _amazon0302()
        held = table[(i - AMAZON0302_HEAD) % len(table)]
        if held == ():
            return [(AMAZON0302_HEAD - 1, i)]
        if held == (0,):
            return [(2, i)]
        return [(i - back, i) for back in held]

    def unlinks(self, i: int) -> list[tuple[int, int]]:
        """The links object i takes over: G.__dict__ takes G.graph and G._node from
        G."""
        return [(0, 1), (0, 2)] if i == 3 else []


@cache
def _amazon0302() -> list[tuple[int, ...]]:
    """What holds each of Amazon0302's objects past the head: () for _adj, (0,)
    for _node, or how many objects back an edge's one or two holders are."""
    data = zlib.decompress(AMAZON0302_LINKS.read_bytes())
    numbers: list[int] = []
    n = shift = 0
    for byte in data:
        n |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            numbers.append(n)
            n = shift = 0
    held: list[tuple[int, ...]] = []
    k = 0
    while k < len(numbers):
        kind = numbers[k]
        k += 1
        if kind < 2:
            held.append(() if kind == 0 else (0,))
            continue
        near, farther = kind - 1, numbers[k]
        k += 1
        held.append((near, near + farther) if farther else (near,))
    return held


# bm_async_tree's tree: the root task and six levels of six tasks under it, each
# level's under a TaskGroup of its parent's.
_BRANCHES = 6
_LEVELS = 6
_TASKS = sum(_BRANCHES**level for level in range(_LEVELS + 1))
_INNER_TASKS = _TASKS - _BRANCHES**_LEVELS
# One simulated object stands for an object of one role in each of 16 tasks that
# asyncio makes and runs one after another (ADR 0002).
_GROUP = 16
_GROUPS = -(-_TASKS // _GROUP)
_INNER_GROUPS = -(-_INNER_TASKS // _GROUP)
# Records: on the reference build, a walk from sys, first in, first out as the
# branch marks, scans 16,520 objects before asyncio's event loop, 7 references
# down. TaskGroups reaches its loop through a path of this many objects, which puts
# it past the objects of start-up's that sys reaches.
TASK_GROUPS_PATH = 10
_LOOP = TASK_GROUPS_PATH
_READY = _LOOP + 1
_TIMERS = _LOOP + 2
# TaskGroups' objects before its tasks': the path, the loop, the loop's queue of
# handles ready to run and its heap of timers.
TASK_GROUPS_HEAD = _LOOP + 3
# Its objects: a group's tasks are made with 7 each, then a group of tasks that
# start TaskGroups makes 8 more as it runs, and a group of leaves 9.
TASK_GROUPS_SIZE = (
    TASK_GROUPS_HEAD + 7 * _GROUPS + 8 * _INNER_GROUPS + 9 * (_GROUPS - _INNER_GROUPS)
)


@dataclass(frozen=True)
class TaskGroups:
    """bm_async_tree's tree of asyncio tasks, as its io variant with --task-groups
    builds it (ADR 0026). sys reaches asyncio's event loop down a path, and the
    loop holds a queue of handles ready to run and a heap of timers. asyncio runs
    the tasks in the order it makes them, a level at a time. A task's parent makes
    it with its coroutine, two Contexts, a done-callback into the parent's
    TaskGroup, and a handle in the ready queue. When the task runs, the queue lets
    go of its handle. A task with children then starts a TaskGroup, whose set
    holds them, and waits on a Future; a leaf sleeps on a Future that a timer
    holds. Each task links back to its parent, and to itself through the Future it
    waits on, and the program cuts those links as the tasks finish. A larger
    structure starts the tree again under the same loop."""

    def cyclic_garbage(self, size: int) -> int:
        return 0

    def links(self, i: int) -> list[tuple[int, int]]:
        if not i:
            return []
        if i <= _LOOP:
            return [(i - 1, i)]
        if i < TASK_GROUPS_HEAD:
            return [(_LOOP, i)]
        return _repeated(i, _task_groups().links)

    def unlinks(self, i: int) -> list[tuple[int, int]]:
        """The links object i's making cuts: a group's tasks' handles leave the
        ready queue as they run."""
        if i < TASK_GROUPS_HEAD:
            return []
        return _repeated(i, _task_groups().unlinks)

    def teardown(self, size: int) -> list[tuple[int, int]]:
        """The links the program cuts among a structure's first `size` objects
        before it goes, which leaves no cycle: each task's links back to its
        parent and to itself."""
        period = len(_task_groups().links)
        cuts: list[tuple[int, int]] = []
        for shift in range(0, size - TASK_GROUPS_HEAD, period):
            cuts += [
                (source + shift, target + shift)
                for source, target in _task_groups().teardown
                if max(source, target) + shift < size
            ]
        return cuts


def _repeated(i: int, table: list[list[tuple[int, int]]]) -> list[tuple[int, int]]:
    """Object i's pairs from the table of one tree's objects past the head, moved
    to the tree object i falls in."""
    repeat, j = divmod(i - TASK_GROUPS_HEAD, len(table))
    shift = repeat * len(table)
    return [
        (
            source + shift if source >= TASK_GROUPS_HEAD else source,
            target + shift if target >= TASK_GROUPS_HEAD else target,
        )
        for source, target in table[j]
    ]


@dataclass
class _TaskTable:
    """One tree's objects past TaskGroups' head: each one's links and the links
    its making cuts, and the links the program cuts before the tree goes."""

    links: list[list[tuple[int, int]]] = field(default_factory=list)
    unlinks: list[list[tuple[int, int]]] = field(default_factory=list)
    teardown: list[tuple[int, int]] = field(default_factory=list)

    def add(
        self,
        *holders: int,
        holds: tuple[int, ...] = (),
        back: tuple[int, ...] = (),
        cut: tuple[tuple[int, int], ...] = (),
    ) -> int:
        """The next object: what holds it, what it holds, what it holds that the
        program lets go before the tree goes, and the links its making cuts."""
        i = TASK_GROUPS_HEAD + len(self.links)
        self.links.append(
            [(holder, i) for holder in holders] + [(i, held) for held in holds + back]
        )
        self.unlinks.append(list(cut))
        self.teardown += [(i, held) for held in back]
        return i


@cache
def _task_groups() -> _TaskTable:
    """The objects of bm_async_tree's tree in the order asyncio makes them."""
    table = _TaskTable()
    task: dict[int, int] = {}
    coroutine: dict[int, int] = {}
    context: dict[int, int] = {}
    handle: dict[int, int] = {}
    task_group: dict[int, int] = {}
    children: dict[int, int] = {}

    def parent(group: int) -> int:
        """The group of the parent of the group's first task."""
        return (_GROUP * group - 1) // _BRANCHES // _GROUP

    def make(group: int) -> None:
        """A group's tasks as their parent's step makes them."""
        if group:
            up = parent(group)
            # The set of the parent's TaskGroup holds a task, which the parent
            # awaits.
            task[group] = table.add(children[up], back=(task[up],))
        else:
            task[group] = table.add(_LOOP)
        coroutine[group] = table.add(task[group])
        context[group] = table.add(task[group])
        table.add(task[group])
        handle[group] = table.add(_READY)
        # The handle's TaskStepMethWrapper.
        table.add(handle[group], holds=(task[group],))
        # The done-callback, a method of the parent's TaskGroup.
        table.add(task[group], back=(task_group[parent(group)],) if group else ())

    def run(group: int, made: list[int]) -> None:
        """A group's tasks as they first run."""
        me = task[group]
        ran = ((_READY, handle[group]),)
        if group < _INNER_GROUPS:
            task_group[group] = table.add(coroutine[group], back=(me,), cut=ran)
            table.add(task_group[group])
            children[group] = table.add(task_group[group])
            for child in made:
                make(child)
            # __aexit__ and _aexit, then the Future they wait on.
            aexit = table.add(coroutine[group], holds=(task_group[group],))
            waiting = table.add(aexit, holds=(task_group[group],))
            future = table.add(task_group[group], me, holds=(context[group],))
            # The Future's wake-up call.
            table.add(future, back=(me,))
        else:
            # workload_func, mock_io_call and asyncio.sleep, then sleep's Future
            # and its wake-up call.
            work = table.add(coroutine[group], cut=ran)
            io = table.add(work)
            waiting = table.add(io)
            future = table.add(waiting, me, holds=(context[group],))
            table.add(future, back=(me,))
            timer = table.add(_TIMERS, waiting)
            # The timer's arguments and its Context.
            table.add(timer, holds=(future,))
            table.add(timer)
        # The FutureIter that awaits the Future.
        table.add(waiting, holds=(future,))

    made: dict[int, list[int]] = defaultdict(list)
    for group in range(1, _GROUPS):
        made[parent(group)].append(group)
    make(0)
    for group in range(_GROUPS):
        run(group, made[group])
    return table


def _scramble(i: int) -> int:
    """i's bits mixed, the same on every run: splitmix64's finaliser."""
    z = (i + 0x9E3779B97F4A7C15) % 2**64
    z = (z ^ z >> 30) * 0xBF58476D1CE4E5B9 % 2**64
    z = (z ^ z >> 27) * 0x94D049BB133111EB % 2**64
    return z ^ z >> 31


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


type Shape = Chains | Tree | Hierarchy | Graph | Amazon0302 | TaskGroups | Rings | Own


def unlinks(shape: Shape, i: int) -> list[tuple[int, int]]:
    """The links object i's making cuts among earlier objects: what it takes over
    from them, or what they let go as it comes."""
    return shape.unlinks(i) if isinstance(shape, Amazon0302 | TaskGroups) else []


def teardown(shape: Shape, size: int) -> list[tuple[int, int]]:
    """The links the program cuts among a structure's first `size` objects before
    the structure goes."""
    return shape.teardown(size) if isinstance(shape, TaskGroups) else []


@dataclass(frozen=True)
class StructureParameters:
    """The workload parameters of one structure. A long-lived structure has no
    lifetime and no rebuild interval."""

    shape: Shape
    size: int
    root: Root
    lifetime: int | None
    rebuild_interval: int | None
    # The churn allocations after each built object. A fraction spreads them: by its
    # k-th object a build has made k times as many, rounded down, so a churn of 1/2
    # follows every second object with one (ADR 0023).
    build_churn: int | Fraction
    # Whether the workload calls `gc.collect()` before each build and after each
    # drop, as create_gc_cycles does.
    full_collections: bool = False
    # Whether a frame holds a structure sys holds while it builds, as a module-level
    # `X = build()` holds what build() makes until it returns: sys takes it once the
    # build ends, its churn included.
    built_in_frame: bool = False
    # Whether C code builds the structure, as a parser builds its tree: an
    # automatic collection that falls due during the build waits until it ends,
    # its churn included (ADR 0022).
    built_in_c: bool = False

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
        # A whole churn reads as an int, however it was given.
        if isinstance(self.build_churn, Fraction) and self.build_churn.is_integer():
            object.__setattr__(self, "build_churn", int(self.build_churn))
        build = self.build_length
        if self.rebuild_interval is not None and build > self.rebuild_interval:
            raise ValueError(
                f"a {build} kB build outlasts its {self.rebuild_interval} kB interval"
            )

    @property
    def build_length(self) -> int:
        """The kB a build takes: its objects and the churn after them."""
        return self.size + math.floor(self.size * self.build_churn)

    def churn_after(self, k: int) -> int:
        """The churn allocations after a build's k-th object."""
        churn = self.build_churn
        return math.floor(k * churn) - math.floor((k - 1) * churn)


class Build:
    """One build of a structure over a heap, one object per kB in its shape's
    order."""

    def __init__(self, heap: Heap, parameters: StructureParameters) -> None:
        self._heap = heap
        self._parameters = parameters
        self._objects: list[int] = []

    @property
    def built(self) -> int:
        """How many of its objects the build has made."""
        return len(self._objects)

    @property
    def done(self) -> bool:
        return len(self._objects) == self._parameters.size

    def add(self) -> None:
        """Allocate the next object and link it in, then let go of its frame root.
        A frame-rooted structure's root keeps its frame root, and a module-rooted
        structure's root hangs off sys instead, unless a frame builds it."""
        heap = self._heap
        objects = self._objects
        x = heap.allocate()
        objects.append(x)
        i = len(objects) - 1
        shape = self._parameters.shape
        for source, target in shape.links(i):
            heap.link(objects[source], objects[target])
        for source, target in unlinks(shape, i):
            heap.unlink(objects[source], objects[target])
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
        """Cut the links the program cuts before the structure goes, then let go of
        its root. What lies on its shape's cycles stays as cyclic garbage, and
        refcounting frees the rest on the spot."""
        heap = self._heap
        objects = self._objects
        for source, target in teardown(self._parameters.shape, len(objects)):
            heap.unlink(objects[source], objects[target])
        root = objects[0]
        unreachable = self._parameters.shape.cyclic_garbage(len(self._objects))
        if self._parameters.root == "module":
            heap.unlink(heap.module_root, root, leaves_unreachable=unreachable)
        else:
            heap.let_go_frame_root(root, leaves_unreachable=unreachable)
