"""Presets: named workloads, each modelling one worker of a pyperformance benchmark
from interpreter start-up to shutdown, over the worker's own length (ADR 0011).

Each number's comment names its source: the benchmark's code, at pyperformance
1.14.0, or the records it is fitted to (#117). The records in data/ are mock until
the rerun, so every number fitted to records is a placeholder for now.
"""

from dataclasses import dataclass
from fractions import Fraction

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import Chains, Rings, StructureParameters, Tree
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

PRESETS = {"create_gc_cycles": CREATE_GC_CYCLES, "json_loads": JSON_LOADS}
