"""Presets: named workloads, each modelling one worker of a pyperformance benchmark
from interpreter start-up to shutdown, over the worker's own length (ADR 0011).

Each number's comment names its source: the benchmark's code, at pyperformance
1.14.0, or the records we fitted it to (#117). A number its comment calls a
placeholder has no source yet: neither the code nor the records in data/ fix it.
"""

from dataclasses import dataclass
from fractions import Fraction

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import (
    Chains,
    Graph,
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
    """A worker's start-up and imports, as five structures (ADR 0011): under the
    module root, chains that refcounting frees at shutdown and a tree that shutdown
    leaves as cyclic garbage; and chains that sys does not reach, which a full
    collection examines where it marks the rest. A frame root holds those until
    shutdown. Two trees start-up lets go of as soon as it builds them, one before
    the module root's structures and one after, give its first two collections the
    cyclic garbage they free."""

    garbage: int
    acyclic: int
    cyclic: int
    late_garbage: int
    unreached: int
    # The churn after each object. It takes in the tuples a collection untracks
    # without examining them, which the simulator does not model (ADR 0011).
    churn: int

    @property
    def structures(self) -> tuple[StructureParameters, ...]:
        def built(
            shape: Shape, size: int, root: Root, lifetime: int | None
        ) -> StructureParameters:
            return StructureParameters(
                shape=shape,
                size=size,
                root=root,
                lifetime=lifetime,
                rebuild_interval=None,
                build_churn=self.churn,
            )

        return (
            built(Tree(), self.garbage, "frame", 0),
            built(Chains(width=16), self.acyclic, "module", None),
            built(Tree(), self.cyclic, "module", None),
            built(Tree(), self.late_garbage, "frame", 0),
            built(Chains(width=16), self.unreached, "frame", None),
        )

    @property
    def length(self) -> int:
        """Its length on the allocation clock, in kB."""
        objects = (
            self.garbage
            + self.acyclic
            + self.cyclic
            + self.late_garbage
            + self.unreached
        )
        return objects * (1 + self.churn)


# Start-up and imports: the interpreter, pyperf and the benchmark's own imports.
# The five benchmarks' first collections agree within 5%, so their presets share
# it. The records give real objects, each 16 to a simulated one (ADR 0002).
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
    # collector. It builds after the cyclic tree, which ends past the first
    # collection, and goes before the second, at 4,000 kB. With the first tree it
    # makes the 216 create_gc_cycles' first gc.collect() frees under the
    # incremental collector.
    late_garbage=5,
    # Records: the 3,705 each of create_gc_cycles' gc.collect() calls examines and
    # keeps under the incremental collector, the rings aside.
    unreached=232,
    # Records: the first collection examines 8,141 to 8,845 real objects at 2,000
    # kB, and start-up ends before the third automatic collection.
    churn=3,
)


# create_gc_cycles, in bm_gc_collect: each loop calls gc.collect(), builds 100 rings
# of 21 Node objects in a list, drops the list and calls gc.collect() again.

# Records: the workers' first gc.collect() starts at 5,484 kB, 860 kB after
# start-up ends.
_SET_UP = 860 // (1 + _START_UP.churn)
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
            # gc.collect(), at start-up's churn. It builds before the loops, as the
            # rings repeat, and refcounting frees it as it ends.
            StructureParameters(
                shape=Chains(width=16),
                size=_SET_UP,
                root="frame",
                lifetime=0,
                rebuild_interval=None,
                build_churn=_START_UP.churn,
            ),
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, what comes before the loops, then the
    # loops, the last ending with its second gc.collect().
    run_length=_START_UP.length
    + _SET_UP * (1 + _START_UP.churn)
    + (_LOOPS - 1) * _LOOP
    + _RINGS,
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
# Records: the automatic collections per worker. Each marks threshold0 kB of
# allocation (ADR 0011), and the records cannot tell where before the next one the
# worker ends, so the run ends about halfway, as json_loads' does.
_XML_COLLECTIONS = 51
# Code: a value's own tree and its 60 parses. pyperf runs a warmup and three values
# a worker, one loop each.
_XML_TREES = 61
_XML_VALUES = 4
# Each tree's slot on the clock, the tree and the parser's other objects: the
# worker's length after start-up over its 244 trees, 403 kB.
_XML_SLOT = (
    (2 * _XML_COLLECTIONS + 1) * CollectorSettings().threshold0 // 2 - _START_UP.length
) // (_XML_VALUES * _XML_TREES)
_XML_VALUE = _XML_TREES * _XML_SLOT

XML_ETREE_PARSE = Preset(
    benchmark="xml_etree_parse",
    workload=WorkloadParameters(
        # The parser's own objects.
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
            # starts and dropped as it ends.
            StructureParameters(
                shape=_XML_SHAPE,
                size=_XML_TREE,
                root="frame",
                lifetime=_XML_VALUE - _XML_TREE,
                rebuild_interval=_XML_VALUE,
                build_churn=0,
            ),
            # Code: the parsed trees, from the file and from the bytes in turn. Each
            # goes as the next of its kind, the next build but one, builds. A
            # value's first parse waits for its own tree and runs into the next
            # slot, which it takes, so a value parses 60.
            StructureParameters(
                shape=_XML_SHAPE,
                size=_XML_TREE,
                root="frame",
                lifetime=2 * _XML_SLOT,
                rebuild_interval=_XML_SLOT,
                build_churn=0,
            ),
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, then its values.
    run_length=_START_UP.length + _XML_VALUES * _XML_VALUE,
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
# Placeholder: the event loop's churn after each task it starts.
_ASYNC_BUILD_CHURN = 1
_ASYNC_TREE = _TASKS * _REAL_PER_TASK // 16
# Records: the automatic collections per worker. Each marks threshold0 kB of
# allocation (ADR 0011), and the records cannot tell where before the next one the
# worker ends, so the run ends about halfway, as json_loads' does.
_ASYNC_COLLECTIONS = 261
# Code: pyperf runs a warmup and three values a worker, one loop each.
_ASYNC_RUNS = 4
# A run's length on the clock: the worker's length after start-up over its runs,
# 129,594 kB.
_ASYNC_RUN = (
    (2 * _ASYNC_COLLECTIONS + 1) * CollectorSettings().threshold0 // 2
    - _START_UP.length
) // _ASYNC_RUNS

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
            # Code: the task tree, built a level at a time as asyncio runs each
            # task after the one that started it. No task links back to its parent,
            # so refcounting frees the tree as the run ends. Records: sys reaches
            # it, through the event loop that runs it. The branch's old collections
            # mark from sys alone, and spend their whole budget while they examine
            # 643 real objects each.
            StructureParameters(
                shape=Hierarchy(branches=6),
                size=_ASYNC_TREE,
                root="module",
                lifetime=_ASYNC_RUN - _ASYNC_TREE * (1 + _ASYNC_BUILD_CHURN),
                rebuild_interval=_ASYNC_RUN,
                build_churn=_ASYNC_BUILD_CHURN,
            ),
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, then its runs.
    run_length=_START_UP.length + _ASYNC_RUNS * _ASYNC_RUN,
)


# connected_components, in bm_networkx: the module loads the Amazon co-purchasing
# graph into its globals before pyperf starts, and each loop counts the graph's
# connected components with a breadth-first walk.

# Code: read_adjlist's 262,111 nodes with two dicts each and 899,792 edges with one,
# 1,424,118 tracked objects in all under networkx 3.4.2: 89,007 simulated objects
# (ADR 0002), with about two edges' dicts to a node's.
_GRAPH = 1_424_118 // 16
_GRAPH_SHAPE = Graph(edges=2)
# Records: the automatic collections per worker. Each marks threshold0 kB of
# allocation (ADR 0011), and the records cannot tell where before the next one the
# worker ends, so the run ends about halfway, as json_loads' does.
_CONNECTED_COMPONENTS_COLLECTIONS = 99
# Code: pyperf runs a warmup and three values a worker, one loop each.
_WALKS = 4
# A loop's length on the clock: the worker's length after start-up and the load
# over its loops, 26,342 kB.
_WALK = (
    (2 * _CONNECTED_COMPONENTS_COLLECTIONS + 1) * CollectorSettings().threshold0 // 2
    - _START_UP.length
    - _GRAPH
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
            *_START_UP.structures,
            # Code: the graph, a global of the benchmark's module until shutdown.
            # G = nx.read_adjlist(...) stores it once read_adjlist returns, and
            # read_adjlist's frame holds it while it loads. Records: the branch's
            # old collections examine it in increments as it loads, up to 231,870
            # real objects in one, and mark it once the module holds it.
            # Records: the heap tops out after the 61st automatic collection,
            # about 118 MB after start-up, so read_adjlist's lists, tuples and
            # throwaway dicts come to about 0.3 kB for each kB of graph. A build's
            # churn comes in whole kB, so the load leaves it out and ends about
            # 29 MB early.
            StructureParameters(
                shape=_GRAPH_SHAPE,
                size=_GRAPH,
                root="module",
                lifetime=None,
                rebuild_interval=None,
                build_churn=0,
                built_in_frame=True,
            ),
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, the load, then its loops.
    run_length=_START_UP.length + _GRAPH + _WALKS * _WALK,
)

PRESETS = {
    "create_gc_cycles": CREATE_GC_CYCLES,
    "json_loads": JSON_LOADS,
    "xml_etree_parse": XML_ETREE_PARSE,
    "async_tree_io_tg": ASYNC_TREE_IO_TG,
    "connected_components": CONNECTED_COMPONENTS,
}
