"""Presets: named workloads, each modelling one worker of a pyperformance benchmark
from interpreter start-up to shutdown, over the worker's own length (ADR 0011).

Each number's comment names its source: the benchmark's code, at pyperformance
1.14.0, or the records we fitted it to (#117). A number its comment calls a
placeholder has no source yet: neither the code nor the records in data/ fix it.
"""

import math
from dataclasses import dataclass, replace
from fractions import Fraction

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import (
    AMAZON0302_SIZE,
    Amazon0302,
    Chains,
    Hierarchy,
    Rings,
    Root,
    Shape,
    StructureParameters,
    Tree,
)
from pep848_sim.workload import ChurnParameters, WorkloadParameters


@dataclass(frozen=True)
class Preset:
    """A preset's workload and run length. Its collector settings are the PEP's
    defaults, which the benchmarks run under."""

    # pyperformance's name for the benchmark, as its records carry it.
    benchmark: str
    workload: WorkloadParameters
    run_length: int


@dataclass(frozen=True)
class _StartUp:
    """A worker's start-up and imports, as six structures (ADR 0011): under the
    module root, chains that refcounting frees at shutdown and a tree that shutdown
    leaves as cyclic garbage; and chains that sys does not reach, which a full
    collection examines where it marks the rest. A frame root holds those until
    shutdown. Two trees start-up lets go of as soon as it builds them, one before
    the module root's structures and one after, give its first two collections the
    cyclic garbage they free.

    Start-up allocates more kB to an object once its first collection has come, so
    the tree under the module root builds in two parts: the first up to that
    collection at one churn, the rest at the other."""

    garbage: int
    acyclic: int
    cyclic: int
    late_garbage: int
    unreached: int
    # The churn after each object, before the first collection and after it. It
    # takes in the tuples a collection untracks without examining them, which the
    # simulator does not model (ADR 0011).
    churn: int | Fraction
    late_churn: int | Fraction

    @property
    def structures(self) -> tuple[StructureParameters, ...]:
        def built(
            shape: Shape,
            size: int,
            root: Root,
            lifetime: int | None,
            churn: int | Fraction,
        ) -> StructureParameters:
            return StructureParameters(
                shape=shape,
                size=size,
                root=root,
                lifetime=lifetime,
                rebuild_interval=None,
                build_churn=churn,
            )

        # The objects that fill the kB up to the first collection, at the PEP's
        # threshold0, and the one it comes in.
        early = math.ceil(CollectorSettings().threshold0 / (1 + self.churn))
        first_tree = early - self.garbage - self.acyclic
        return (
            built(Tree(), self.garbage, "frame", 0, self.churn),
            built(Chains(width=16), self.acyclic, "module", None, self.churn),
            built(Tree(), first_tree, "module", None, self.churn),
            built(Tree(), self.late_garbage, "frame", 0, self.late_churn),
            built(Tree(), self.cyclic - first_tree, "module", None, self.late_churn),
            built(Chains(width=16), self.unreached, "frame", None, self.late_churn),
        )

    @property
    def length(self) -> int:
        """Its length on the allocation clock, in kB."""
        return sum(s.build_length for s in self.structures)

    def set_up(
        self,
        length: int,
        churn: int | Fraction | None = None,
        lifetime: int | None = 0,
    ) -> StructureParameters:
        """What a worker allocates after start-up and before its loops, `length` kB
        at `churn`, or start-up's late churn: chains that build once, before the
        loops repeat, and that refcounting frees `lifetime` kB after they end, or
        never (ADR 0011)."""
        churn = self.late_churn if churn is None else churn
        return StructureParameters(
            shape=Chains(width=16),
            size=length // (1 + churn),
            root="frame",
            lifetime=lifetime,
            rebuild_interval=None,
            build_churn=churn,
        )


# Start-up and imports: the interpreter, pyperf and the benchmark's own imports.
# The five benchmarks' first collections agree within 5%, so their presets share
# it, and connected_components' takes a late churn of its own (ADR 0011). The
# records give real objects, each 16 to a simulated one (ADR 0002).
_START_UP = _StartUp(
    # Records: the 129 the first collection frees under the legacy collector.
    garbage=8,
    # Records: what create_gc_cycles' full collections keep, 18,291, less the
    # other two.
    acyclic=121,
    # Records: the 12,637 finalize_modules' first collection frees, where gcmon
    # caught it.
    cyclic=790,
    # Records: the 84 and 3 the second and third collections free under the legacy
    # collector. It builds after the cyclic tree's first part, which ends just past
    # the first collection, and goes before the second, at 4,000 kB. With the
    # first tree it makes the 216 create_gc_cycles' first gc.collect() frees under
    # the incremental collector.
    late_garbage=5,
    # Records: the 3,705 each of create_gc_cycles' gc.collect() calls examines and
    # keeps under the incremental collector, the rings aside.
    unreached=232,
    # Records: the first collection examines 8,141 to 8,845 real objects at 2,000
    # kB.
    churn=Fraction(278, 100),
    # Records: the second examines 5,855 to 6,352 at 4,000 kB, but for
    # connected_components'.
    late_churn=Fraction(422, 100),
)


# create_gc_cycles, in bm_gc_collect: each loop calls gc.collect(), builds 100 rings
# of 21 Node objects in a list, drops the list and calls gc.collect() again.

# Records: the workers' first gc.collect() starts at 5,484 kB.
_SET_UP = _START_UP.set_up(5_484 - _START_UP.length)
# Code: the list, and the rings' 2,100 nodes as 131 simulated objects (ADR 0002),
# each a ring of its own, as a ring of 21 comes to about one.
_RINGS = 132
# Records: a loop allocates 180.5 kB between its two calls, its rings and nothing
# else that outlives it: the nodes come to 88 B each, where ADR 0002 counts 64 B
# a real object. At each gc.collect() the heap holds 18,291 or 20,391 real
# objects in every worker, the rings' 2,100 apart. A build allocates its objects
# alone, so churn makes up the rest after the second call.
_LOOP = 181
# Records: the incremental workers' 1,024 gc.collect() calls, two a loop. pyperf
# calibrated the legacy workers to 64 loops a value, not 128, so they ran 256.
_LOOPS = 512

CREATE_GC_CYCLES = Preset(
    benchmark="create_gc_cycles",
    workload=WorkloadParameters(
        # A loop leaves no room for churn, so start-up's build churn is all of it.
        # Records: the young collections find almost no cycles. A lifetime of 1 kB
        # or 4 moves what they examine by 0.2%, so it takes json_loads' 1.
        churn=ChurnParameters(
            cycle_share=Fraction(0),
            cycle_size=1,
            lifetime_mean=1,
            long_share=Fraction(0),
            long_lifetimes=(1, 1),
        ),
        structures=(
            *_START_UP.structures,
            # Code: a local of the benchmark's function, dropped as soon as it is
            # built, with gc.collect() before each build and after each drop.
            StructureParameters(
                shape=Rings(length=1),
                size=_RINGS,
                root="frame",
                lifetime=0,
                rebuild_interval=_LOOP,
                build_churn=0,
                full_collections=True,
            ),
            # Records: what the workers allocate after start-up, before their first
            # gc.collect().
            _SET_UP,
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, what comes before the loops, then the
    # loops, the last ending with its second gc.collect().
    run_length=(
        _START_UP.length + _SET_UP.build_length + (_LOOPS - 1) * _LOOP + _RINGS
    ),
)


# json_loads, in bm_json_loads: each loop calls json.loads 60 times, 20 times on
# each of three strings, and drops each result as the call returns. The module's
# globals, DICT, TUPLE and the copies of DICT, come to a few real objects, which
# start-up takes in.

# Records: the automatic collections a worker makes under the incremental
# collector. Each marks threshold0 kB of allocation (ADR 0011), and the run ends
# halfway to the next, at 21,000 kB. The one worker whose shutdown gcmon caught
# ended at 20,438. pyperf calibrated the legacy workers to 512 loops a value, not
# 256, so they made 17 and a gen 1 collection, past the run's reach.
_JSON_LOADS_COLLECTIONS = 10

JSON_LOADS = Preset(
    benchmark="json_loads",
    workload=WorkloadParameters(
        churn=ChurnParameters(
            # Code: no result holds a cycle, and each goes as its call returns. A
            # loop's 60 results come to about 400 real objects, 25 kB of churn.
            cycle_share=Fraction(0),
            cycle_size=1,
            lifetime_mean=1,
            # Records: no churn outlives a collection. Past start-up, each legacy
            # gen 0 collection examines 2 to 6 real objects, 65 at the last, and
            # the heap holds 18,890 real objects at each, give or take 4.
            long_share=Fraction(0),
            long_lifetimes=(1, 1),
        ),
        structures=_START_UP.structures,
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, then loops of churn up to its last
    # automatic collection and halfway to the next.
    run_length=(2 * _JSON_LOADS_COLLECTIONS + 1) * CollectorSettings().threshold0 // 2,
)


# xml_etree_parse, in bm_xml_etree, pyperf's --worker-task=0: each value builds a
# tree of elements, writes it to a file and runs one loop, which parses the file and
# the tree's bytes 30 times each. Each parse's tree replaces the last of its kind.

# Code: 5,103 elements and the dicts of the 53 with attributes, 322 simulated
# objects (ADR 0002). The root holds 50 children of 100 subchildren each, so 50
# branches keep the tree two levels deep, as all its elements are but a chain of
# 50, and no element links back to its parent.
_XML_TREE = 322
_XML_SHAPE = Hierarchy(branches=50)
# Records: a parse allocates 360 kB, 72 B an element where ADR 0002 counts 64 B a
# real object. Each parse's slot on the clock holds its tree, then churn for the
# rest, as a build allocates its objects alone. The workers' collections come six
# parses apart while they parse, 2,162 kB, as each waits for the parse under way
# to return (ADR 0022).
_XML_SLOT = 360
# Records: building a value's own tree, serialising it and writing it allocate
# 3,864 kB before its first parse. The workers' collections come threshold0 kB
# apart there.
_XML_PYTHON = 3_864
# Records: the workers' third collection examines 9,199 real objects at 6,000 kB,
# start-up's last and the whole tree, so the tree builds with 1 kB of churn after
# each object.
_XML_TREE_CHURN = 1
_XML_TREE_BUILD = _XML_TREE * (1 + _XML_TREE_CHURN)
# Records: a worker's values run 25,468 kB each. A value takes 71 slots, 25,560 kB,
# so that each value's parses fall in the same slots. pyperf runs a warmup and
# three values a worker, one loop each.
_XML_VALUE = 71 * _XML_SLOT
_XML_VALUES = 4
# Code: tostring's and write's lists and tuples, which go as each call returns.
# Records: the workers' fourth collection examines 1,029 real objects at 8,000 kB,
# 30 kB of churn after each. They fill the rest of the value's Python.
_XML_SERIALISING_CHURN = 30
_XML_SERIALISING = StructureParameters(
    shape=Chains(width=16),
    size=(_XML_PYTHON - _XML_TREE_BUILD) // (1 + _XML_SERIALISING_CHURN),
    root="frame",
    lifetime=0,
    rebuild_interval=_XML_VALUE,
    build_churn=_XML_SERIALISING_CHURN,
)
# Code: each parsed tree goes as the next parse but one returns, two slots on, and
# the collection that waits for that parse still finds it. A value's first parse
# starts as soon as the value has built and serialised its own tree, 123 kB ahead
# of its slot, so its tree lives that much longer to see the third parse return,
# and the rest as long. Records: the workers' gen 0 collections examine three
# parsed trees while they parse, 15,480 real objects.
_XML_PARSED_LIFETIME = (
    2 * _XML_SLOT + -(_XML_TREE_BUILD + _XML_SERIALISING.build_length) % _XML_SLOT + 1
)
# Records: the workers' third collection frees 36 real objects, where the other
# benchmarks' free 3: xml.etree's imports let go of cycles of their own. Their
# first late collection starts at 10,215 to 10,229 kB and examines three parsed
# trees, so it follows their third parse, and their parses start at about 9,150
# kB. Their first value starts at 5,284 kB, as soon as these have built.
_XML_GARBAGE = StructureParameters(
    shape=Tree(),
    size=2,
    root="frame",
    lifetime=0,
    rebuild_interval=None,
    build_churn=_START_UP.late_churn,
)
# Records: the workers start shutdown at 109,612 kB, past their last value. pyperf
# and the last value's serialising allocate the rest, which the run takes as the
# start of a fifth value.
_XML_SHUTDOWN = 109_612

XML_ETREE_PARSE = Preset(
    benchmark="xml_etree_parse",
    workload=WorkloadParameters(
        # The rest of each parse's slot, and the serialising of each value's tree.
        churn=ChurnParameters(
            # Records: each worker's collections free 249 real objects under either
            # collector, all start-up's, so the parser makes no cycles. The cycles
            # xml_etree's young collections find come from its iterparse task.
            cycle_share=Fraction(0),
            cycle_size=1,
            # The records leave it open: a mean of 1 kB and one of 4 kB make the
            # same collections.
            lifetime_mean=1,
            long_share=Fraction(0),
            long_lifetimes=(1, 1),
        ),
        structures=(
            *_START_UP.structures,
            # Code: build_xml_tree's tree, a local of bench_etree, built as each value
            # starts. Records: the workers' young collections still find it after
            # the value ends, at their 27th, 39th and 51st collections, so it goes as
            # the next value's tree has built.
            StructureParameters(
                shape=_XML_SHAPE,
                size=_XML_TREE,
                root="frame",
                lifetime=_XML_VALUE,
                rebuild_interval=_XML_VALUE,
                build_churn=_XML_TREE_CHURN,
            ),
            _XML_SERIALISING,
            # Code: the parsed trees, from the file and from the bytes in turn. A
            # value's first parse waits for its own tree and runs into the next
            # slot, which it takes, so a value parses 60. The C accelerator's
            # parser builds each tree in C.
            StructureParameters(
                shape=_XML_SHAPE,
                size=_XML_TREE,
                root="frame",
                lifetime=_XML_PARSED_LIFETIME,
                rebuild_interval=_XML_SLOT,
                build_churn=0,
                built_in_c=True,
            ),
            _XML_GARBAGE,
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, its values and what follows them.
    run_length=_XML_SHUTDOWN,
)


# async_tree_io_tg, in bm_async_tree with "io --task-groups": each run starts a tree
# of asyncio tasks six levels deep, each level's six under a TaskGroup of its
# parent's, and each leaf sleeps 50 ms. A task goes as it finishes, and the whole
# tree by the run's end.

# Code: the root task and six levels of six branches under it.
_TASKS = sum(6**level for level in range(7))
# Records: real objects to a task, with its coroutine, its group and its sleep's
# future and timer handle. A worker's heap peaks at 857,000 to 866,000 real
# objects, less start-up's.
_REAL_PER_TASK = 15
_ASYNC_TREE = _TASKS * _REAL_PER_TASK // 16
# Records: the legacy collector's gen 0 collections examine 15,260 to 15,600 real
# objects each while a tree builds, and the first builds from about 7,500 kB to
# about 123,000. The event loop's handles and callbacks come to 1.17 kB for each kB
# of tree (ADR 0023).
_ASYNC_BUILD_CHURN = Fraction(117, 100)
# Records: the heap grows faster once a tree has built, peaks about 6 MB on, and
# falls to start-up's by the next run. Meanwhile the legacy collector's gen 0
# collections examine 22,000 to 39,388 real objects each, 26,000 on average: 0.23
# kB of churn for each kB the finishing tasks keep.
_ASYNC_FINISH_CHURN = Fraction(23, 100)
# Records: the workers' third tree stands at their 193rd collection, a gen 1, 6.4
# MB after it has built: the collection examines 199,934 real objects. The tree
# goes 8 MB on.
_ASYNC_TREE_LIFETIME = 8_000
# Records: the gen 0 collections fall back to 15,600 or below about 2 MB before
# each run ends: 954 real objects at the 197th.
_ASYNC_FINISHED_EARLY = 2_000
# Records: the workers' first tree starts at 7,524 kB. Their third collection
# examines 5,294 real objects at 6,000 kB, 7.26 kB of churn after each object, and
# their fourth 6,901 at 8,000 kB, as the tree starts: what the set-up allocated
# since the third outlives it. It stays to shutdown: their gen 2 collection,
# between two trees, examines 30,468, 6,700 more than start-up's.
_ASYNC_SET_UP = _START_UP.set_up(
    7_524 - _START_UP.length, churn=Fraction(726, 100), lifetime=None
)
# Records: the automatic collections per worker. Each marks threshold0 kB of
# allocation (ADR 0011), and the records cannot tell where before the next one the
# worker ends, so the run ends about halfway, as json_loads' does.
_ASYNC_COLLECTIONS = 261
# Code: pyperf runs a warmup and three values a worker, one loop each.
_ASYNC_RUNS = 4
# A run's length on the clock: the worker's length after start-up and the set-up
# over its runs, 128,869 kB.
_ASYNC_RUN = (
    (2 * _ASYNC_COLLECTIONS + 1) * CollectorSettings().threshold0 // 2
    - _START_UP.length
    - _ASYNC_SET_UP.build_length
) // _ASYNC_RUNS
# Code: the task tree, built a level at a time as asyncio runs each task after the
# one that started it. No task links back to its parent, so refcounting frees it as
# its tasks finish, here at once. Records: sys reaches
# it, through the event loop that runs it. The branch's old collections mark from
# sys alone, and spend their whole budget while they examine 643 real objects each.
_ASYNC_TASK_TREE = StructureParameters(
    shape=Hierarchy(branches=6),
    size=_ASYNC_TREE,
    root="module",
    lifetime=_ASYNC_TREE_LIFETIME,
    rebuild_interval=_ASYNC_RUN,
    build_churn=_ASYNC_BUILD_CHURN,
)
# Records: what the tasks allocate as they finish and keep until the last one has,
# reached through the event loop as the tree is. It fills the run up to the last
# 2 MB, and goes as it ends.
_ASYNC_FINISH_ROOM = _ASYNC_RUN - _ASYNC_TASK_TREE.build_length - _ASYNC_FINISHED_EARLY
_ASYNC_FINISH = _ASYNC_FINISH_ROOM // (1 + _ASYNC_FINISH_CHURN)
_ASYNC_FINISHED = StructureParameters(
    shape=Chains(width=16),
    size=_ASYNC_FINISH,
    root="module",
    lifetime=_ASYNC_FINISH_ROOM
    - _ASYNC_FINISH
    - int(_ASYNC_FINISH * _ASYNC_FINISH_CHURN),
    rebuild_interval=_ASYNC_RUN,
    build_churn=_ASYNC_FINISH_CHURN,
)

ASYNC_TREE_IO_TG = Preset(
    benchmark="async_tree_io_tg",
    workload=WorkloadParameters(
        # Placeholders: the event loop's handles and callbacks, in which the
        # records' collections find almost no cycles.
        churn=ChurnParameters(
            cycle_share=Fraction(0),
            cycle_size=1,
            lifetime_mean=4,
            long_share=Fraction(0),
            long_lifetimes=(1, 1),
        ),
        structures=(
            *_START_UP.structures,
            _ASYNC_TASK_TREE,
            _ASYNC_FINISHED,
            _ASYNC_SET_UP,
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, the set-up, then its runs.
    run_length=(
        _START_UP.length + _ASYNC_SET_UP.build_length + _ASYNC_RUNS * _ASYNC_RUN
    ),
)


# connected_components, in bm_networkx: the module imports networkx and loads the
# Amazon co-purchasing graph into its globals before pyperf starts, and each loop
# counts the graph's connected components with a breadth-first walk.

# Records: the workers' second collection examines 5,658 real objects, where the
# other benchmarks' examine 5,855 to 6,352, so start-up allocates more kB to an
# object past the first.
_CC_START_UP = replace(_START_UP, late_churn=Fraction(466, 100))
# Code: networkx's argmap decorators compile a wrapper on a function's first call,
# and the compiling leaves cycles: closures that reach themselves through their
# cells, a Signature and its Parameters. read_adjlist's and empty_graph's come as
# the load starts. Records: the workers' young collection at 38,004 kB frees 133
# real objects, where it examines what was allocated about 14,000 kB.
_LOAD_WRAPPERS = StructureParameters(
    shape=Tree(),
    size=133 // 16,
    root="frame",
    lifetime=0,
    rebuild_interval=None,
    build_churn=0,
)
# Code: read_adjlist opens the file and wraps it in a generator of lines before it
# makes the graph, and its frame holds them while it reads. Records: once the
# branch's increment from _adj has taken the graph, at the 30th collection, the
# sweep waits for its budget until the 48th, which examines the last 153 real
# objects pending and ends it.
_READER = StructureParameters(
    shape=Chains(width=1),
    size=153 // 16 + 1,
    root="frame",
    lifetime=AMAZON0302_SIZE + math.floor(AMAZON0302_SIZE * Fraction(24, 100)),
    rebuild_interval=None,
    build_churn=0,
)
# Code: networkx's modules, functions and classes, globals of sys.modules until
# shutdown. Records: the legacy collector's gen 0 collections examine 4,400 to 4,800
# real objects each between start-up and the load, which starts at about 14,600 kB:
# 6 kB of churn after each object.
_NETWORKX = StructureParameters(
    shape=Chains(width=16),
    size=(
        14_600
        - _CC_START_UP.length
        - _LOAD_WRAPPERS.build_length
        - _READER.build_length
    )
    // 7,
    root="module",
    lifetime=None,
    rebuild_interval=None,
    build_churn=6,
)
# Code: the graph, a global of the benchmark's module until shutdown, which
# read_adjlist builds from bm_networkx's own file: 1,424,118 tracked objects under
# networkx 3.4.2, 89,007 simulated ones (ADR 0002), each standing for one in 16 of
# the file's in the order read_adjlist makes them (ADR 0025).
# graph = networkx.read_adjlist(...) stores it once read_adjlist returns, and
# read_adjlist's frame holds it while it loads, which here is to shutdown. Records:
# the branch's old collections take it about 50,000 real objects at a time, a
# budget each, but for _node's increment of 85,797 at the 24th collection and
# _adj's of 231,870 at the 30th, in a sweep that takes young objects too (ADR
# 0024). The next five young collections examine 6,600 to 13,600 each: the
# attribute dicts _node, visited by then, holds.
# Records: the legacy collector's gen 0 collections examine 24,700 to 27,600 real
# objects each while it loads, and the 63rd, at 126,005 kB, half as many. The load
# ends there, so read_adjlist's lists, tuples and throwaway dicts come to 0.24 kB for
# each kB of graph (ADR 0023).
_GRAPH_LOAD = StructureParameters(
    shape=Amazon0302(),
    size=AMAZON0302_SIZE,
    root="frame",
    lifetime=None,
    rebuild_interval=None,
    build_churn=Fraction(24, 100),
)
# Code: connected_components' own wrapper, compiled at the first loop's call.
# Records: the workers' young collection at 146,006 kB frees 32 real objects, of
# what was allocated as the load ended.
_WALK_WRAPPER = replace(_LOAD_WRAPPERS, size=32 // 16)
# Records: the automatic collections per worker. Each marks threshold0 kB of
# allocation (ADR 0011), and the records cannot tell where before the next one the
# worker ends, so the run ends about halfway, as json_loads' does.
_CONNECTED_COMPONENTS_COLLECTIONS = 99
# Code: pyperf runs a warmup and three values a worker, one loop each.
_WALKS = 4
# A loop's length on the clock: the worker's length after start-up, the imports and
# the load over its loops, 18,508 kB.
_WALK = (
    (2 * _CONNECTED_COMPONENTS_COLLECTIONS + 1) * CollectorSettings().threshold0 // 2
    - _CC_START_UP.length
    - _NETWORKX.build_length
    - _LOAD_WRAPPERS.build_length
    - _READER.build_length
    - _GRAPH_LOAD.build_length
    - _WALK_WRAPPER.build_length
) // _WALKS

CONNECTED_COMPONENTS = Preset(
    benchmark="connected_components",
    workload=WorkloadParameters(
        churn=ChurnParameters(
            # Code: the walk's key iterator over each node's neighbours goes once
            # they run out, and nothing it makes holds a cycle.
            cycle_share=Fraction(0),
            cycle_size=1,
            lifetime_mean=1,
            # Placeholders: what outlives a collection, such as each level's list.
            long_share=Fraction(0),
            long_lifetimes=(1, 1),
        ),
        structures=(
            *_CC_START_UP.structures,
            _NETWORKX,
            _LOAD_WRAPPERS,
            _READER,
            _GRAPH_LOAD,
            _WALK_WRAPPER,
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, the imports, the load, then its loops.
    run_length=(
        _CC_START_UP.length
        + _NETWORKX.build_length
        + _LOAD_WRAPPERS.build_length
        + _READER.build_length
        + _GRAPH_LOAD.build_length
        + _WALK_WRAPPER.build_length
        + _WALKS * _WALK
    ),
)

PRESETS = {
    "create_gc_cycles": CREATE_GC_CYCLES,
    "json_loads": JSON_LOADS,
    "xml_etree_parse": XML_ETREE_PARSE,
    "async_tree_io_tg": ASYNC_TREE_IO_TG,
    "connected_components": CONNECTED_COMPONENTS,
}
