import hashlib
import json
from collections.abc import Iterable
from fractions import Fraction
from typing import override

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import Collector, CollectorSettings, Record
from pep848_sim.collectors.heap import Heap
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.run import run
from pep848_sim.structures import Chains, StructureParameters, Tree
from pep848_sim.workload import ChurnParameters, WorkloadParameters
from test_workload import churn_parameters, structure_parameters

COLLECTORS: tuple[type[Collector], ...] = (IncrementalCollector, LegacyCollector)

CHURN = ChurnParameters(Fraction(1, 4), 3, 5, Fraction(1, 20), (20, 60))

# Each object the workload allocates, with the allocation clock at the time.
Allocations = list[tuple[int, int]]


class NotingIncremental(IncrementalCollector):
    def __init__(self, settings: CollectorSettings, allocations: Allocations) -> None:
        super().__init__(settings)
        self.allocations = allocations

    @override
    def attach(self, heap: Heap) -> None:
        super().attach(heap)
        self.heap = heap

    @override
    def add(self, x: int) -> None:
        super().add(x)
        if x != self.heap.module_root:  # the heap makes sys before the run begins
            self.allocations.append((self.heap.clock, x))


class NotingLegacy(LegacyCollector):
    def __init__(self, settings: CollectorSettings, allocations: Allocations) -> None:
        super().__init__(settings)
        self.allocations = allocations

    @override
    def attach(self, heap: Heap) -> None:
        super().attach(heap)
        self.heap = heap

    @override
    def add(self, x: int) -> None:
        super().add(x)
        if x != self.heap.module_root:  # the heap makes sys before the run begins
            self.allocations.append((self.heap.clock, x))


@st.composite
def workloads(draw: st.DrawFn) -> WorkloadParameters:
    return WorkloadParameters(
        draw(churn_parameters()),
        tuple(draw(st.lists(structure_parameters(), max_size=2))),
        draw(st.integers(min_value=0, max_value=2**32)),
        draw(st.booleans()),
    )


def collector_settings() -> st.SearchStrategy[CollectorSettings]:
    return st.builds(
        CollectorSettings,
        st.integers(min_value=1, max_value=20),
        st.integers(min_value=1, max_value=10),
        st.integers(min_value=0, max_value=3),
    )


def records(parts: Iterable[list[Record]]) -> list[Record]:
    return [record for part in parts for record in part]


@given(
    workloads(),
    st.sampled_from(COLLECTORS),
    collector_settings(),
    st.integers(min_value=0, max_value=600),
    st.integers(min_value=1, max_value=5),
)
def test_a_run_yields_its_newest_records_every_few_collections(
    parameters: WorkloadParameters,
    collector: type[Collector],
    settings: CollectorSettings,
    run_length: int,
    every: int,
) -> None:
    parts = list(run(parameters, collector, settings, run_length, every))
    # More than any of these runs collects: one part, at the end.
    whole = list(run(parameters, collector, settings, run_length, 10**6))

    assert len(whole) <= 1
    assert [len(part) for part in parts[:-1]] == [every] * (len(parts) - 1)
    assert [] not in parts
    assert records(parts) == records(whole)


@pytest.mark.parametrize("collector", COLLECTORS)
@pytest.mark.parametrize(
    ("run_length", "clocks"),
    [
        (29, [10, 20]),
        # On a boundary, the run collects as its next allocation would.
        (30, [10, 20, 30]),
    ],
)
def test_a_run_that_ends_on_a_boundary_collects_there(
    collector: type[Collector], run_length: int, clocks: list[int]
) -> None:
    parameters = WorkloadParameters(CHURN, (), seed=1)
    settings = CollectorSettings(threshold0=10)

    parts = run(parameters, collector, settings, run_length, every=1)

    assert [record.clock for record in records(parts)] == clocks


@pytest.mark.parametrize("collector", COLLECTORS)
def test_a_run_that_asks_for_shutdown_ends_with_two_full_collections(
    collector: type[Collector],
) -> None:
    parameters = WorkloadParameters(CHURN, (), seed=1, shutdown=True)
    settings = CollectorSettings(threshold0=10)

    parts = run(parameters, collector, settings, 29, every=1)

    whole = records(parts)
    assert [(record.clock, record.kind) for record in whole[2:]] == [
        (29, "shutdown"),
        (29, "shutdown"),
    ]
    assert [record.clock for record in whole[:2]] == [10, 20]
    # The first frees all the cyclic garbage, the cycles the frames held among it,
    # and leaves the second none.
    first, second = whole[2:]
    assert sum(first.spaces_after) == first.reachable_after
    assert second.freed == 0


@given(
    workloads(),
    collector_settings(),
    st.integers(min_value=0, max_value=600),
)
def test_both_collectors_runs_allocate_the_same_objects_at_the_same_clocks(
    parameters: WorkloadParameters, settings: CollectorSettings, run_length: int
) -> None:
    incremental: Allocations = []
    legacy: Allocations = []

    incremental_parts = run(
        parameters, lambda s: NotingIncremental(s, incremental), settings, run_length, 1
    )
    incremental_clocks = [record.clock for record in records(incremental_parts)]
    legacy_parts = run(
        parameters, lambda s: NotingLegacy(s, legacy), settings, run_length, 1
    )
    legacy_clocks = [record.clock for record in records(legacy_parts)]

    assert incremental == legacy
    # Both collect at the same boundaries.
    assert incremental_clocks == legacy_clocks


# Under the default threshold1 and threshold2 with threshold0 at 20, the
# incremental run ends three sweeps and the legacy run makes seven gen 2
# collections.
FIXED = WorkloadParameters(
    ChurnParameters(Fraction(1, 4), 3, 200, Fraction(1, 20), (100, 1_000)),
    (
        StructureParameters(Chains(16), 1_000, "module", None, None, 0),
        StructureParameters(Tree(), 100, "frame", 400, 1_000, 1),
    ),
    seed=848,
)


def digest(records: list[Record]) -> str:
    """The first 16 hex digits of the SHA-256 of the records as compact JSON."""
    text = json.dumps(records, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize(
    ("collector", "pinned"),
    [
        (IncrementalCollector, "c679a9492b62551a"),
        (LegacyCollector, "8eb3fc9dd9e3d903"),
    ],
)
def test_a_fixed_workloads_records_keep_their_digest(
    collector: type[Collector], pinned: str
) -> None:
    """Pinned under CPython, which ADR 0007 makes Pyodide's digest too."""
    parts = run(FIXED, collector, CollectorSettings(threshold0=20), 20_000, every=50)

    assert digest(records(parts)) == pinned
