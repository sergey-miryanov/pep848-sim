"""What a workload does to its heap.

Every draw is exact (ADR 0007): integers from the run's own generator, and
thresholds built from exact ratios of integers, with no C-library floating point.
"""

from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from random import Random

from pep848_sim.heap import Heap

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


@dataclass(frozen=True)
class ChurnParameters:
    """The workload parameters of background churn."""

    # The fate mix: the share of churn allocations that start a cycle.
    cycle_share: Fraction
    cycle_size: int
    # The churn lifetimes, in kB.
    lifetime_mean: int
    long_share: Fraction
    long_lifetimes: tuple[int, int]


class Churn:
    """Background churn over a heap, one kB at a time: transients, and small cycles
    that become cyclic garbage when their lifetimes end.

    It makes only the transients a collection can see (ADR 0005), unless told to
    make every one, which draws the same lifetimes and lets the tests compare."""

    def __init__(
        self,
        heap: Heap,
        rng: Random,
        parameters: ChurnParameters,
        threshold0: int,
        *,
        make_every_transient: bool = False,
    ) -> None:
        self._heap = heap
        self._rng = rng
        self._parameters = parameters
        self._lifetimes = ChurnLifetimes(
            parameters.lifetime_mean, parameters.long_share, parameters.long_lifetimes
        )
        self._threshold0 = threshold0
        self._make_every_transient = make_every_transient
        # The members of the cycle being built, one per kB.
        self._cycle: list[int] = []
        # By the clock value a lifetime ends at: each frame root to let go of then,
        # with how many objects letting go of it leaves unreachable.
        self._ends: dict[int, list[tuple[int, int]]] = {}

    def run_to(self, clock: int) -> None:
        """Churn until the allocation clock reads `clock`."""
        heap = self._heap
        while heap.clock < clock:
            if self._cycle or chance(self._rng, self._parameters.cycle_share):
                self._build_cycle()
            else:
                self._transient()
            # Within each kB the clock moves, then the workload lets go of each
            # lifetime that ends there (ADR 0005).
            for x, unreachable in self._ends.pop(heap.clock, ()):
                heap.let_go_frame_root(x, leaves_unreachable=unreachable)

    def _build_cycle(self) -> None:
        """Allocate the cycle's next member, linked from the one before. The first
        member's allocating root holds the cycle until its lifetime ends."""
        heap = self._heap
        x = heap.allocate()
        if self._cycle:
            heap.link(self._cycle[-1], x)
            heap.let_go_frame_root(x)
        self._cycle.append(x)
        if len(self._cycle) == self._parameters.cycle_size:
            heap.link(x, self._cycle[0])
            ends = heap.clock + self._lifetimes.cycle(self._rng)
            self._end_at(ends, self._cycle[0], len(self._cycle))
            self._cycle = []

    def _transient(self) -> None:
        heap = self._heap
        made_in = heap.clock + 1
        ends = made_in + self._lifetimes.transient(self._rng)
        # The first collection to come runs at the first boundary at or after the
        # kB the transient is made in, after that kB's let-gos.
        boundary = -(-made_in // self._threshold0) * self._threshold0
        if ends <= boundary and not self._make_every_transient:
            heap.allocate_unseen()
            return
        x = heap.allocate()
        self._end_at(ends, x, 0)

    def _end_at(self, clock: int, x: int, leaves_unreachable: int) -> None:
        self._ends.setdefault(clock, []).append((x, leaves_unreachable))
