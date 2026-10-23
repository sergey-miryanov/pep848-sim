"""Presets: named workloads, each modelling one worker of a pyperformance benchmark
from interpreter start-up to shutdown, over the worker's own length (ADR 0011).

Each number's comment names its source: the benchmark's code, at pyperformance
1.14.0, or the records it is fitted to (#117). The records in data/ are mock until
the rerun, so every number fitted to records is a placeholder for now.
"""

from dataclasses import dataclass
from fractions import Fraction

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import (
    Chains,
    Hierarchy,
    Rings,
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
    """A worker's start-up and imports, under the module root, as two structures:
    chains that refcounting frees at shutdown, and a tree that shutdown leaves as
    cyclic garbage (ADR 0011). The records' first heap_size sets their sum, and
    shutdown's yield the split between them."""

    acyclic: int
    cyclic: int
    # The churn after each object, for the automatic collections the records hold
    # before the benchmark's loops begin.
    churn: int

    @property
    def structures(self) -> tuple[StructureParameters, StructureParameters]:
        return (
            StructureParameters(
                shape=Chains(width=16),
                size=self.acyclic,
                root="module",
                lifetime=None,
                rebuild_interval=None,
                build_churn=self.churn,
            ),
            StructureParameters(
                shape=Tree(),
                size=self.cyclic,
                root="module",
                lifetime=None,
                rebuild_interval=None,
                build_churn=self.churn,
            ),
        )

    @property
    def length(self) -> int:
        """Its length on the allocation clock, in kB."""
        return (self.acyclic + self.cyclic) * (1 + self.churn)


# create_gc_cycles, in bm_gc_collect: each loop calls gc.collect(), builds 100 rings
# of 21 Node objects in a list, drops the list and calls gc.collect() again.

# Start-up and imports: the interpreter, pyperf and gc. Placeholders until the
# rerun, which holds two automatic collections before the first loop.
_CREATE_GC_CYCLES_START_UP = _StartUp(acyclic=350, cyclic=350, churn=6)
# Code: 2,100 nodes, 131 simulated objects (ADR 0002), each ring of 21 rounded to
# one, and the list.
_RINGS = 132
# A loop: the rings' build, and pyperf's bookkeeping as churn, a placeholder 8 kB.
# Start-up fills whole loops, so each loop starts as its interval comes round.
_LOOP = 140
# Placeholder: half the records' gc.collect() calls per worker.
_LOOPS = 512

CREATE_GC_CYCLES = Preset(
    benchmark="create_gc_cycles",
    workload=WorkloadParameters(
        # Placeholders. The records' young collections find almost no cycles, so
        # the churn makes none.
        churn=ChurnParameters(
            cycle_share=Fraction(0),
            cycle_size=1,
            lifetime_mean=4,
            long_share=Fraction(0),
            long_lifetimes=(1, 1),
        ),
        structures=(
            *_CREATE_GC_CYCLES_START_UP.structures,
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
        ),
        seed=848,
        shutdown=True,
    ),
    # The worker's own length: start-up, then its loops, the last ending with its
    # second gc.collect().
    run_length=_CREATE_GC_CYCLES_START_UP.length + (_LOOPS - 1) * _LOOP + _RINGS,
)


# json_loads, in bm_json_loads: each loop calls json.loads 60 times, 20 times on
# each of three strings, and drops each result as the call returns.

# Start-up and imports: the interpreter, pyperf, json and random. The module's
# globals, DICT, TUPLE and the copies of DICT, come to a few real objects, which
# start-up's size takes in. Placeholders until the rerun.
_JSON_LOADS_START_UP = _StartUp(acyclic=350, cyclic=350, churn=6)
# Placeholder: the records' automatic collections per worker. Each marks threshold0
# kB of allocation (ADR 0011), and the records cannot tell where before the next
# one the worker ends, so the run ends halfway.
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
            # Placeholders: pyperf's bookkeeping between loops, which keeps some
            # objects alive across a collection.
            long_share=Fraction(1, 50),
            long_lifetimes=(100, 1000),
        ),
        structures=_JSON_LOADS_START_UP.structures,
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

# Start-up and imports: the interpreter, pyperf, xml.etree.ElementTree with its C
# accelerator, and tempfile. Placeholders until the rerun.
_XML_ETREE_PARSE_START_UP = _StartUp(acyclic=350, cyclic=350, churn=6)
# Code: 5,103 elements and the dicts of the 53 with attributes, 322 simulated
# objects (ADR 0002). The root holds 50 children of 100 subchildren each, so 50
# branches keep the tree two levels deep, as nearly all its elements are, and no
# element links back to its parent.
_XML_TREE = 322
_XML_SHAPE = Hierarchy(branches=50)
# Placeholder: each tree's slot on the clock, the tree and the parser's other
# objects: the records' automatic collections over a worker's 244 trees.
_XML_SLOT = 420
# Code: a value's own tree and its 60 parses. pyperf runs a warmup and three values
# a worker, one loop each.
_XML_VALUE = 61 * _XML_SLOT
_XML_VALUES = 4

XML_ETREE_PARSE = Preset(
    benchmark="xml_etree_parse",
    workload=WorkloadParameters(
        # Placeholders: the parser's own objects, and the cycles the records' young
        # collections find, which the code does not show.
        churn=ChurnParameters(
            cycle_share=Fraction(1, 50),
            cycle_size=2,
            lifetime_mean=4,
            long_share=Fraction(0),
            long_lifetimes=(1, 1),
        ),
        structures=(
            *_XML_ETREE_PARSE_START_UP.structures,
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
            # Code: the parsed trees, from the file and from the bytes in turn, each
            # dropped as the next of its kind, the next build but one, is built. A
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
    run_length=_XML_ETREE_PARSE_START_UP.length + _XML_VALUES * _XML_VALUE,
)

PRESETS = {
    "create_gc_cycles": CREATE_GC_CYCLES,
    "json_loads": JSON_LOADS,
    "xml_etree_parse": XML_ETREE_PARSE,
}
