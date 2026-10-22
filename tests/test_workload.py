from fractions import Fraction
from random import Random

from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collector import Collector
from pep848_sim.heap import Heap
from pep848_sim.workload import (
    Churn,
    ChurnLifetimes,
    ChurnParameters,
    geometric_thresholds,
)
from test_heap import reachable

LIFETIMES = ChurnLifetimes(
    mean=16, long_share=Fraction(1, 500), long_lifetimes=(30_000, 300_000)
)
DRAWS = 200_000
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


def test_thresholds_for_a_mean_of_4_kb_match_the_closed_form() -> None:
    # P(lifetime <= kb) = 1 - (3/4)**kb, and 2**32 times it is an integer up to 16 kB.
    expected = [2**32 - 3**kb * 2 ** (32 - 2 * kb) for kb in range(1, 17)]

    assert geometric_thresholds(4)[:16] == expected


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

    Churn(heap, Random(848), CHURN, threshold0=2_000).run_to(run_kb)

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
    collector = Collector()
    heap = Heap(collector)
    churn = Churn(heap, Random(seed), parameters, threshold0)

    for stop in sorted(stops):
        churn.run_to(stop)

        assert heap.clock == stop
        # Nothing collects, so the nursery holds every alive object.
        unreachable = set(collector.nursery) - reachable(heap)
        assert heap.uncollected_garbage == len(unreachable)


def test_a_transient_let_go_by_the_next_boundary_moves_the_clock_alone() -> None:
    # A mean of 1 kB: each transient ends in the kB after the one it was made in.
    parameters = ChurnParameters(
        cycle_share=Fraction(0),
        cycle_size=1,
        lifetime_mean=1,
        long_share=Fraction(0),
        long_lifetimes=(1, 1),
    )
    lazy, eager = Heap(Collector()), Heap(Collector())
    lazy_churn = Churn(lazy, Random(848), parameters, threshold0=10)
    eager_churn = Churn(
        eager, Random(848), parameters, threshold0=10, make_every_transient=True
    )

    # sys, and the transient made in the kB, if the run made it. The one made in
    # kB 9 ends at the boundary at 10, and the one made in kB 11 well before the
    # boundary at 20, so the lazy run makes neither. The one made in kB 10 outlasts
    # the boundary there, so both runs make it.
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
    lazy_collector, eager_collector = Collector(), Collector()
    lazy, eager = Heap(lazy_collector), Heap(eager_collector)
    lazy_churn = Churn(lazy, Random(seed), parameters, threshold0)
    eager_churn = Churn(
        eager, Random(seed), parameters, threshold0, make_every_transient=True
    )

    for boundary in range(threshold0, threshold0 * (boundaries + 1), threshold0):
        lazy_churn.run_to(boundary)
        eager_churn.run_to(boundary)

        assert renamed(lazy, lazy_collector) == renamed(eager, eager_collector)
