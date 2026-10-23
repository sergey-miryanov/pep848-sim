"""Presets: named workloads, each modelling one worker of a pyperformance benchmark
from interpreter start-up to shutdown, over the worker's own length (ADR 0011).

Each number's comment names its source: the benchmark's code, at pyperformance
1.14.0, or the records it is fitted to (#117). The records in data/ are mock until
the rerun, so every number fitted to records is a placeholder for now.
"""

from dataclasses import dataclass
from fractions import Fraction

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


# create_gc_cycles, in bm_gc_collect: each loop calls gc.collect(), builds 100 rings
# of 21 Node objects in a list, drops the list and calls gc.collect() again.

# Start-up and imports, under the module root: the interpreter, pyperf and gc.
# Placeholders until the rerun: the records' first heap_size sets their sum, and
# shutdown's yield the split between what turns into cyclic garbage and what
# refcounting frees (ADR 0011).
_START_UP_ACYCLIC = 350
_START_UP_CYCLIC = 350
# Placeholder: the churn after each start-up object, for the two automatic
# collections the records hold before the first loop (ADR 0011).
_START_UP_CHURN = 6
_START_UP = (_START_UP_ACYCLIC + _START_UP_CYCLIC) * (1 + _START_UP_CHURN)
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
            StructureParameters(
                shape=Chains(width=16),
                size=_START_UP_ACYCLIC,
                root="module",
                lifetime=None,
                rebuild_interval=None,
                build_churn=_START_UP_CHURN,
            ),
            StructureParameters(
                shape=Tree(),
                size=_START_UP_CYCLIC,
                root="module",
                lifetime=None,
                rebuild_interval=None,
                build_churn=_START_UP_CHURN,
            ),
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
    run_length=_START_UP + (_LOOPS - 1) * _LOOP + _RINGS,
)

PRESETS = {"create_gc_cycles": CREATE_GC_CYCLES}
