from fractions import Fraction
from itertools import pairwise
from random import Random

from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import Collector, CollectorSettings
from pep848_sim.collectors.heap import Heap
from pep848_sim.collectors.incremental import IncrementalCollector
from pep848_sim.collectors.legacy import LegacyCollector
from pep848_sim.structures import (
    Chains,
    Graph,
    Hierarchy,
    Rings,
    Root,
    StructureParameters,
    Tree,
)
from pep848_sim.workload import (
    Churn,
    ChurnLifetimes,
    ChurnParameters,
    Workload,
    WorkloadParameters,
    geometric_thresholds,
)
from test_heap import Recording, reachable, reached_from
from test_structures import own_shapes

LIFETIMES = ChurnLifetimes(
    mean=16, long_share=Fraction(1, 500), long_lifetimes=(30_000, 300_000)
)
DRAWS = 200_000
# Churn that makes no object while boundaries stay far apart: each transient ends in
# the kB after its own.
QUIET = ChurnParameters(
    cycle_share=Fraction(0),
    cycle_size=1,
    lifetime_mean=1,
    long_share=Fraction(0),
    long_lifetimes=(1, 1),
)
CHURN = ChurnParameters(
    cycle_share=Fraction(3, 100),
    cycle_size=3,
    lifetime_mean=16,
    long_share=Fraction(1, 500),
    long_lifetimes=(30_000, 300_000),
)


@st.composite
def churn_parameters(draw: st.DrawFn) -> ChurnParameters:
    """Small churn, so that a short run crosses many lifetimes and boundaries."""
    long_from = draw(st.integers(min_value=1, max_value=100))
    return ChurnParameters(
        cycle_share=Fraction(draw(st.integers(min_value=0, max_value=4)), 4),
        cycle_size=draw(st.integers(min_value=1, max_value=4)),
        lifetime_mean=draw(st.integers(min_value=1, max_value=20)),
        long_share=Fraction(draw(st.integers(min_value=0, max_value=4)), 20),
        long_lifetimes=(long_from, long_from + draw(st.integers(0, 100))),
    )


ROOTS: tuple[Root, ...] = ("module", "frame")


@st.composite
def structure_parameters(draw: st.DrawFn, own: bool = True) -> StructureParameters:
    """A small structure of any shape, a reader's own too unless `own` is false,
    and either root, sys's built in a frame or not: long-lived, built once and
    dropped, or repeating."""
    size = draw(st.integers(min_value=1, max_value=6))
    build_churn = Fraction(draw(st.integers(min_value=0, max_value=8)), 4)
    build = size + size * build_churn.numerator // build_churn.denominator
    kind = draw(st.sampled_from(["long-lived", "once", "repeating"]))
    shapes = [
        st.builds(Chains, st.integers(1, 4)),
        st.just(Tree()),
        st.builds(Hierarchy, st.integers(1, 4)),
        st.builds(Graph, st.integers(0, 3)),
        st.builds(Rings, st.integers(1, 4)),
    ]
    root = draw(st.sampled_from(ROOTS))
    return StructureParameters(
        shape=draw(st.one_of(*shapes, *([own_shapes()] if own else []))),
        size=size,
        root=root,
        lifetime=None if kind == "long-lived" else draw(st.integers(1, 60)),
        rebuild_interval=(
            draw(st.integers(build, build + 40)) if kind == "repeating" else None
        ),
        build_churn=build_churn,
        full_collections=draw(st.booleans()),
        built_in_frame=root == "module" and draw(st.booleans()),
        built_in_c=draw(st.booleans()),
    )


def test_thresholds_for_a_mean_of_4_kb_match_the_closed_form() -> None:
    # P(lifetime <= kb) = 1 - (3/4)**kb, and 2**32 times it is an integer up to 16 kB.
    expected = [2**32 - 3**kb * 2 ** (32 - 2 * kb) for kb in range(1, 17)]

    assert geometric_thresholds(4)[:16] == expected


def exact_thresholds(mean: int) -> list[int]:
    """The thresholds as the first build made them, each from an exact ratio of
    two growing ints: the reference a faster build must match."""
    outlast, of = 1, 1
    thresholds: list[int] = []
    while not thresholds or thresholds[-1] < 2**32:
        outlast *= mean - 1
        of *= mean
        thresholds.append(2**32 - 2**32 * outlast // of)
    return thresholds


@given(st.integers(min_value=1, max_value=300))
def test_thresholds_match_the_exact_build(mean: int) -> None:
    assert geometric_thresholds(mean) == exact_thresholds(mean)


@given(st.integers(min_value=1, max_value=60), st.integers(min_value=1, max_value=8))
def test_thresholds_match_the_exact_build_on_few_guard_bits(
    mean: int, guard_bits: int
) -> None:
    # So few bits send many thresholds down the slow exact path, and small means
    # keep it quick.
    assert geometric_thresholds(mean, guard_bits=guard_bits) == exact_thresholds(mean)


def test_a_long_draw_of_transient_lifetimes_keeps_the_mean_and_the_long_share() -> None:
    rng = Random(848)

    draws = [LIFETIMES.transient(rng) for _ in range(DRAWS)]

    short = [d for d in draws if d < 30_000]
    long = [d for d in draws if d >= 30_000]
    # Five standard deviations: 0.18 kB on the mean, 0.0005 on the long share, and
    # 20,000 kB on the long lifetimes' mean.
    assert abs(sum(short) / len(short) - 16) < 0.18
    assert abs(len(long) / DRAWS - 1 / 500) < 0.0005
    assert abs(sum(long) / len(long) - 165_000) < 20_000
    assert min(short) == 1
    assert max(long) <= 300_000


def test_a_cycle_draws_a_geometric_lifetime_never_a_long_one() -> None:
    rng = Random(848)

    draws = [LIFETIMES.cycle(rng) for _ in range(DRAWS)]

    assert abs(sum(draws) / DRAWS - 16) < 0.18
    assert max(draws) < 30_000


def test_a_long_run_starts_cycles_at_the_fate_mix() -> None:
    heap = Heap(Collector())
    run_kb = 100_000

    Churn(heap, Random(848), CHURN).run_to(run_kb)

    # Nothing collects, so the count holds every cycle let go of: all but the one
    # or two still held at the end.
    cycles = heap.uncollected_garbage // 3
    transients = run_kb - 3 * cycles
    # Five standard deviations of the share over about 94,000 allocations.
    assert abs(cycles / (cycles + transients) - 3 / 100) < 0.003


@given(
    churn_parameters(),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=50),
    st.lists(st.integers(min_value=0, max_value=300), max_size=4),
)
def test_churn_stops_where_asked_and_counts_the_cycles_it_lets_go_of(
    parameters: ChurnParameters, seed: int, threshold0: int, stops: list[int]
) -> None:
    collector = Collector(CollectorSettings(threshold0=threshold0))
    heap = Heap(collector)
    churn = Churn(heap, Random(seed), parameters)

    for stop in sorted(stops):
        churn.run_to(stop)

        assert heap.clock == stop
        # Nothing collects, so the nursery holds every alive object.
        unreachable = set(collector.nursery) - reachable(heap)
        assert heap.uncollected_garbage == len(unreachable)


def test_a_transient_let_go_by_the_next_boundary_moves_the_clock_alone() -> None:
    # A mean of 1 kB: each transient ends in the kB after its own.
    parameters = ChurnParameters(
        cycle_share=Fraction(0),
        cycle_size=1,
        lifetime_mean=1,
        long_share=Fraction(0),
        long_lifetimes=(1, 1),
    )
    settings = CollectorSettings(threshold0=10)
    lazy, eager = Heap(Collector(settings)), Heap(Collector(settings))
    lazy_churn = Churn(lazy, Random(848), parameters)
    eager_churn = Churn(eager, Random(848), parameters, make_every_transient=True)

    # sys, and the kB's transient, if the run made it. The transient of kB 9 ends
    # at the boundary at 10, and that of kB 11 before the boundary at 20, so the
    # lazy run makes neither. The transient of kB 10 outlasts the boundary there,
    # so both runs make it.
    for clock, alive in [(9, (1, 2)), (10, (2, 2)), (11, (1, 2))]:
        lazy_churn.run_to(clock)
        eager_churn.run_to(clock)

        assert (len(lazy), len(eager)) == alive


def renamed(heap: Heap, collector: Collector) -> tuple[int, list[tuple[int, ...]]]:
    """The heap with each object renamed to its place in the nursery: its count,
    its frame roots and the places it references, with the uncollected garbage."""
    places = {x: i for i, x in enumerate(collector.nursery)}
    frame_roots = heap.frame_roots()
    return heap.uncollected_garbage, [
        (
            heap.reference_count(x),
            frame_roots.get(x, 0),
            *(places[target] for target in heap.references(x)),
        )
        for x in places
    ]


@given(
    churn_parameters(),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=50),
    st.integers(min_value=1, max_value=8),
)
def test_at_every_boundary_the_heap_matches_a_run_that_makes_every_transient(
    parameters: ChurnParameters, seed: int, threshold0: int, boundaries: int
) -> None:
    settings = CollectorSettings(threshold0=threshold0)
    lazy_collector, eager_collector = Collector(settings), Collector(settings)
    lazy, eager = Heap(lazy_collector), Heap(eager_collector)
    lazy_churn = Churn(lazy, Random(seed), parameters)
    eager_churn = Churn(eager, Random(seed), parameters, make_every_transient=True)

    for boundary in range(threshold0, threshold0 * (boundaries + 1), threshold0):
        lazy_churn.run_to(boundary)
        eager_churn.run_to(boundary)

        assert renamed(lazy, lazy_collector) == renamed(eager, eager_collector)


@given(
    st.sampled_from([IncrementalCollector, LegacyCollector]),
    churn_parameters(),
    st.lists(structure_parameters(), max_size=2),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=0, max_value=400),
    st.booleans(),
)
def test_every_collection_matches_a_run_that_makes_every_transient(
    collector: type[IncrementalCollector | LegacyCollector],
    churn: ChurnParameters,
    structures: list[StructureParameters],
    seed: int,
    threshold0: int,
    run_kb: int,
    shutdown: bool,
) -> None:
    """Full collections and shutdown's included (ADR 0005)."""
    settings = CollectorSettings(threshold0=threshold0)
    parameters = WorkloadParameters(churn, tuple(structures), seed)
    lazy_collector, eager_collector = collector(settings), collector(settings)
    lazy = Workload(Heap(lazy_collector), parameters)
    eager = Workload(Heap(eager_collector), parameters, make_every_transient=True)

    for workload in (lazy, eager):
        workload.run_to(run_kb)
        if shutdown:
            workload.shut_down()

    assert lazy_collector.records == eager_collector.records


def test_a_repeating_structure_builds_where_its_rebuild_interval_puts_it() -> None:
    heap = Heap(Collector(CollectorSettings(threshold0=1_000)))
    tree = StructureParameters(
        shape=Tree(),
        size=5,
        root="module",
        lifetime=30,
        rebuild_interval=50,
        build_churn=0,
    )
    parameters = WorkloadParameters(churn=QUIET, structures=(tree,), seed=848)
    workload = Workload(heap, parameters)

    starts: list[int] = []
    drops: list[int] = []
    roots: set[int] = set()
    for kb in range(1, 201):
        workload.run_to(kb)
        now = set(heap.references(heap.module_root))
        if now - roots:
            starts.append(kb)
        if roots - now:
            drops.append(kb)
        roots = now

    assert starts == [1, 51, 101, 151]
    # Each tree lives 30 kB from the end of its 5 kB build.
    assert drops == [35, 85, 135, 185]


def test_the_builds_churn_follows_each_built_object() -> None:
    collector = Collector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    # Churn that makes a cycle of one object with every allocation.
    cycles = ChurnParameters(
        cycle_share=Fraction(1),
        cycle_size=1,
        lifetime_mean=1,
        long_share=Fraction(0),
        long_lifetimes=(1, 1),
    )
    chain = StructureParameters(
        shape=Chains(width=1),
        size=3,
        root="module",
        lifetime=50,
        rebuild_interval=100,
        build_churn=2,
    )
    parameters = WorkloadParameters(churn=cycles, structures=(chain,), seed=848)

    Workload(heap, parameters).run_to(9)

    structure = reached_from(heap, [heap.module_root])
    built = [x in structure for x in collector.nursery]
    assert built == [True, *[True, False, False] * 3]


def test_a_fraction_of_churn_follows_some_built_objects_and_not_others() -> None:
    collector = Collector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    # Churn that makes a cycle of one object with every allocation.
    cycles = ChurnParameters(
        cycle_share=Fraction(1),
        cycle_size=1,
        lifetime_mean=1,
        long_share=Fraction(0),
        long_lifetimes=(1, 1),
    )
    chain = StructureParameters(
        shape=Chains(width=1),
        size=4,
        root="module",
        lifetime=None,
        rebuild_interval=None,
        build_churn=Fraction(1, 2),
    )
    parameters = WorkloadParameters(churn=cycles, structures=(chain,), seed=848)

    Workload(heap, parameters).run_to(6)

    # sys, then two objects and a churn allocation, twice.
    structure = reached_from(heap, [heap.module_root])
    built = [x in structure for x in collector.nursery]
    assert built == [True, *[True, True, False] * 2]


def test_sys_takes_a_structure_built_in_a_frame_once_its_builds_churn_ends() -> None:
    heap = Heap(Collector(CollectorSettings(threshold0=1_000)))
    chain = StructureParameters(
        shape=Chains(width=1),
        size=2,
        root="module",
        lifetime=None,
        rebuild_interval=None,
        build_churn=1,
        built_in_frame=True,
    )
    workload = Workload(
        heap, WorkloadParameters(churn=QUIET, structures=(chain,), seed=848)
    )

    # Its objects come at kB 1 and 3, each with a kB of churn after it, and the
    # build ends with the churn at kB 4.
    workload.run_to(3)
    assert heap.references(heap.module_root) == ()

    workload.run_to(4)
    assert heap.references(heap.module_root) == (1,)


def test_structures_without_an_interval_build_first_and_the_others_wait() -> None:
    heap = Heap(Collector(CollectorSettings(threshold0=1_000)))
    long_lived = StructureParameters(
        shape=Chains(width=1),
        size=2,
        root="module",
        lifetime=None,
        rebuild_interval=None,
        build_churn=0,
    )
    repeating = StructureParameters(
        shape=Tree(),
        size=2,
        root="frame",
        lifetime=5,
        rebuild_interval=20,
        build_churn=0,
    )
    one_off = StructureParameters(
        shape=Chains(width=1),
        size=3,
        root="frame",
        lifetime=10,
        rebuild_interval=None,
        build_churn=0,
    )
    structures = (long_lived, repeating, one_off)
    parameters = WorkloadParameters(churn=QUIET, structures=structures, seed=848)
    workload = Workload(heap, parameters)

    workload.run_to(30)

    # (structure, first kB, last kB): the repeating one falls due once the others
    # have built, at 5, and again at 25.
    assert workload.builds == [(0, 1, 2), (2, 3, 5), (1, 6, 7), (1, 26, 27)]


@given(
    churn_parameters(),
    st.lists(structure_parameters(), min_size=1, max_size=3),
    st.integers(min_value=0, max_value=2**32),
    st.integers(min_value=1, max_value=50),
    st.lists(st.integers(min_value=0, max_value=400), max_size=4),
)
def test_a_workload_runs_to_any_point_and_its_builds_never_overlap(
    churn: ChurnParameters,
    structures: list[StructureParameters],
    seed: int,
    threshold0: int,
    stops: list[int],
) -> None:
    collector = Collector(CollectorSettings(threshold0=threshold0))
    heap = Heap(collector)
    parameters = WorkloadParameters(churn, tuple(structures), seed)
    workload = Workload(heap, parameters)

    for stop in sorted(stops):
        workload.run_to(stop)

        assert heap.clock == stop
        unreachable = set(collector.nursery) - reachable(heap)
        assert heap.uncollected_garbage == len(unreachable)

    builds = workload.builds
    assert all(last < first for (_, _, last), (_, first, _) in pairwise(builds))
    for i, first, last in builds:
        structure = structures[i]
        assert last - first + 1 == structure.build_length
    interval = structures[0].rebuild_interval
    if len(structures) == 1 and interval is not None:
        starts = [first for _, first, _ in builds]
        assert starts == [k * interval + 1 for k in range(len(builds))]


def test_a_structure_that_falls_due_again_while_waiting_skips_that_rebuild() -> None:
    def repeating(size: int, interval: int) -> StructureParameters:
        return StructureParameters(
            shape=Chains(width=1),
            size=size,
            root="frame",
            lifetime=1,
            rebuild_interval=interval,
            build_churn=0,
        )

    heap = Heap(Collector(CollectorSettings(threshold0=1_000)))
    structures = (repeating(2, 10), repeating(50, 100))
    parameters = WorkloadParameters(churn=QUIET, structures=structures, seed=848)
    workload = Workload(heap, parameters)

    workload.run_to(70)

    # The short one falls due at 10, 20, 30, 40 and 50 while the long one builds,
    # and builds once after it.
    assert workload.builds == [(0, 1, 2), (1, 3, 52), (0, 53, 54), (0, 61, 62)]


def test_a_collection_follows_the_let_gos_of_the_kb_before_it() -> None:
    collector = Recording(threshold0=6)
    heap = Heap(collector)
    tree = StructureParameters(
        shape=Tree(),
        size=3,
        root="module",
        lifetime=3,
        rebuild_interval=None,
        build_churn=0,
    )
    parameters = WorkloadParameters(churn=QUIET, structures=(tree,), seed=848)

    Workload(heap, parameters).run_to(7)

    # The tree's build ends in kB 3, and its lifetime in kB 6, on the boundary.
    assert collector.garbage == [3]


def test_a_build_in_c_holds_back_a_collection_until_its_churn_ends() -> None:
    collector = Recording(threshold0=4)
    heap = Heap(collector)
    chain = StructureParameters(
        shape=Chains(width=1),
        size=3,
        root="frame",
        lifetime=0,
        rebuild_interval=10,
        build_churn=1,
        built_in_c=True,
    )
    parameters = WorkloadParameters(churn=QUIET, structures=(chain,), seed=848)

    Workload(heap, parameters).run_to(24)

    # Builds take kB 1 to 6, 11 to 16 and 21 to 26. The budget runs out at 4 and
    # the build holds the collection back to 6; again at 10, between builds, and
    # at 14, within one, which holds it back to 16. The next is due at 20.
    assert collector.clocks == [6, 10, 16, 20]


def test_a_structure_that_asks_gets_a_full_collection_around_each_build() -> None:
    collector = Recording(threshold0=1_000)
    heap = Heap(collector)
    tree = StructureParameters(
        shape=Tree(),
        size=3,
        root="frame",
        lifetime=4,
        rebuild_interval=10,
        build_churn=0,
        full_collections=True,
    )
    parameters = WorkloadParameters(churn=QUIET, structures=(tree,), seed=848)

    Workload(heap, parameters).run_to(25)

    # Builds start after kB 0, 10 and 20 and take three kB each. The first two
    # drops come four kB after their builds end, and the third would at 27.
    assert collector.full == [
        (0, "full"),
        (7, "full"),
        (10, "full"),
        (17, "full"),
        (20, "full"),
    ]


def long_lived(shape: Chains | Tree, size: int, root: Root) -> StructureParameters:
    return StructureParameters(
        shape=shape,
        size=size,
        root=root,
        lifetime=None,
        rebuild_interval=None,
        build_churn=0,
    )


def test_shutdown_lets_go_of_frames_and_modules_and_collects_three_times() -> None:
    collector = Recording(threshold0=1_000)
    heap = Heap(collector)
    structures = (
        long_lived(Tree(), 3, "frame"),
        long_lived(Tree(), 2, "module"),
        long_lived(Chains(width=1), 2, "module"),
    )
    workload = Workload(heap, WorkloadParameters(QUIET, structures, seed=848))
    workload.run_to(9)

    workload.shut_down()

    # Both trees stay as cyclic garbage, and refcounting frees the chain.
    assert heap.frame_roots() == {}
    assert heap.references(heap.module_root) == ()
    assert heap.uncollected_garbage == 5
    assert len(heap) == 6
    assert collector.full == [(9, "shutdown")] * 3


def test_shutdown_collects_once_its_frames_go_and_again_once_its_modules_go() -> None:
    collector = LegacyCollector(CollectorSettings(threshold0=1_000))
    heap = Heap(collector)
    structures = (long_lived(Tree(), 3, "frame"), long_lived(Tree(), 2, "module"))
    workload = Workload(heap, WorkloadParameters(QUIET, structures, seed=848))
    workload.run_to(5)

    workload.shut_down()

    # As _Py_Finalize's PyGC_Collect() frees what the frames left before
    # finalize_modules lets go of the modules and collects twice.
    assert [(record.kind, record.freed) for record in collector.records] == [
        ("shutdown", 3),
        ("shutdown", 2),
        ("shutdown", 0),
    ]
