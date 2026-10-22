"""What a workload does to its heap.

Every draw is exact (ADR 0007): integers from the run's own generator, and
thresholds built from exact ratios of integers, with no C-library floating point.
"""

from bisect import bisect_right
from fractions import Fraction
from random import Random

# A draw is getrandbits(32), one word of the generator, and a threshold splits its
# 2**32 outcomes.
_BITS = 32
_OUTCOMES = 1 << _BITS


def geometric_thresholds(mean: int) -> list[int]:
    """Thresholds for a geometric lifetime on 1, 2, 3 kB and up: the l-th is 2**32
    times P(lifetime <= l), rounded up. The last is 2**32, which folds the tail past
    it into its kB."""
    # (mean - 1)**l / mean**l of the lifetimes outlast l kB. Two ints keep the ratio
    # exact without the gcd a Fraction takes at every step.
    outlast, of = 1, 1
    thresholds: list[int] = []
    while not thresholds or thresholds[-1] < _OUTCOMES:
        outlast *= mean - 1
        of *= mean
        thresholds.append(_OUTCOMES - _OUTCOMES * outlast // of)
    return thresholds


def chance(rng: Random, share: Fraction) -> bool:
    """Whether a draw lands in `share` of the outcomes, exactly."""
    return rng.randrange(share.denominator) < share.numerator


class ChurnLifetimes:
    """The lifetimes background churn draws, in kB."""

    def __init__(
        self, mean: int, long_share: Fraction, long_lifetimes: tuple[int, int]
    ) -> None:
        self._thresholds = geometric_thresholds(mean)
        self._long_share = long_share
        self._long_lifetimes = long_lifetimes

    def transient(self, rng: Random) -> int:
        """A geometric lifetime, or for the long share one drawn evenly from the
        long lifetimes."""
        if chance(rng, self._long_share):
            return rng.randint(*self._long_lifetimes)
        return self._geometric(rng)

    def cycle(self, rng: Random) -> int:
        """A geometric lifetime, never a long one."""
        return self._geometric(rng)

    def _geometric(self, rng: Random) -> int:
        return 1 + bisect_right(self._thresholds, rng.getrandbits(_BITS))
