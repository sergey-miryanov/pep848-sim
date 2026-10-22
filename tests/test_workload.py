from fractions import Fraction
from random import Random

from pep848_sim.workload import ChurnLifetimes, geometric_thresholds

LIFETIMES = ChurnLifetimes(
    mean=16, long_share=Fraction(1, 500), long_lifetimes=(30_000, 300_000)
)
DRAWS = 200_000


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
