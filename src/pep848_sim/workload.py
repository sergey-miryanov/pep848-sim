"""What a workload does to its heap.

Every draw is exact (ADR 0007): integers from the run's own generator, and
lifetime thresholds exact to the outcome, built from integers alone, with no
C-library floating point.
"""

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from functools import partial
from random import Random

from pep848_sim.collectors.heap import Heap
from pep848_sim.structures import Build, StructureParameters

# A draw is getrandbits(32), one word of the generator, and a lifetime threshold
# splits its 2**32 outcomes.
_BITS = 32
_OUTCOMES = 1 << _BITS


def geometric_thresholds(mean: int, *, guard_bits: int = 64) -> list[int]:
    """Thresholds for a geometric lifetime on 1, 2, 3 kB and up: the l-th is 2**32
    times P(lifetime <= l), rounded up. The last is 2**32, which folds the tail past
    it into its kB."""
    # (mean - 1)**l / mean**l of the lifetimes outlast l kB. `scaled` holds 2**32
    # times that with `guard_bits` more bits, rounded down at each kB, so it falls
    # short by less than `mean`. Where the shortfall could reach a whole outcome,
    # the exact ratio of two ints settles it; those ints grow with l, and building
    # every threshold from them took seconds for a mean of a few thousand kB.
    scaled = _OUTCOMES << guard_bits
    thresholds: list[int] = []
    while not thresholds or thresholds[-1] < _OUTCOMES:
        scaled = scaled * (mean - 1) // mean
        outlast = scaled >> guard_bits
        if (scaled + mean) >> guard_bits != outlast:
            kb = len(thresholds) + 1
            outlast = _OUTCOMES * (mean - 1) ** kb // mean**kb
        thresholds.append(_OUTCOMES - outlast)
    return thresholds


def chance(rng: Random, share: Fraction) -> bool:
    """Whether a draw lands in `share` of the outcomes, with no rounding."""
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
        """A geometric lifetime, or for the long share one from the long lifetimes,
        each kB in their range as likely as the next."""
        if chance(rng, self._long_share):
            return rng.randint(*self._long_lifetimes)
        return self._geometric(rng)

    def cycle(self, rng: Random) -> int:
        """A geometric lifetime, never a long one."""
        return self._geometric(rng)

    def _geometric(self, rng: Random) -> int:
        return 1 + bisect_right(self._thresholds, rng.getrandbits(_BITS))


class LetGos:
    """What a workload lets go of, by the clock value each lifetime ends at."""

    def __init__(self) -> None:
        self._at: dict[int, list[Callable[[], None]]] = {}

    def at(self, clock: int, let_go: Callable[[], None]) -> None:
        self._at.setdefault(clock, []).append(let_go)

    def run(self, clock: int) -> None:
        """Let go of each lifetime that ends at `clock`."""
        for let_go in self._at.pop(clock, ()):
            let_go()


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

    def __post_init__(self) -> None:
        for name, share in ("cycle", self.cycle_share), ("long", self.long_share):
            if not 0 <= share <= 1:
                raise ValueError(f"a {name} share of {share} lies outside 0 to 1")
        if self.cycle_size < 1:
            raise ValueError(f"a cycle of {self.cycle_size} objects holds none")
        if self.lifetime_mean < 1:
            raise ValueError(
                f"a churn lifetime mean of {self.lifetime_mean} kB falls under 1 kB"
            )
        low, high = self.long_lifetimes
        if not 1 <= low <= high:
            raise ValueError(f"long lifetimes cannot run from {low} kB to {high} kB")


class Churn:
    """Background churn over a heap, one kB at a time: transients, and small cycles
    that become cyclic garbage when their lifetimes end.

    It makes only the transients a collection can see (ADR 0005), unless the caller
    asks for every one with `make_every_transient`. Both ways draw the same
    lifetimes, so the tests can compare them. A workload hands it the schedule of
    let-gos it shares with its structures, and if it calls `gc.collect()`, the
    earliest clock it could next call it at."""

    def __init__(
        self,
        heap: Heap,
        rng: Random,
        parameters: ChurnParameters,
        *,
        make_every_transient: bool = False,
        let_gos: LetGos | None = None,
        next_full_collection: Callable[[], int | None] | None = None,
    ) -> None:
        self._heap = heap
        self._rng = rng
        self._parameters = parameters
        self._lifetimes = ChurnLifetimes(
            parameters.lifetime_mean, parameters.long_share, parameters.long_lifetimes
        )
        self._make_every_transient = make_every_transient
        self._next_full_collection = next_full_collection
        # The members of the cycle being built, one per kB.
        self._cycle: list[int] = []
        self._let_gos = LetGos() if let_gos is None else let_gos

    def run_to(self, clock: int) -> None:
        """Churn until the allocation clock reads `clock`."""
        heap = self._heap
        while heap.clock < clock:
            self.step()
            # Within each kB the clock moves, then the workload lets go of each
            # lifetime that ends there (ADR 0005).
            self._let_gos.run(heap.clock)

    def step(self) -> None:
        """Make one churn allocation, a transient or a cycle's next member: 1 kB."""
        if self._cycle or chance(self._rng, self._parameters.cycle_share):
            self._build_cycle()
        else:
            self._transient()

    def _build_cycle(self) -> None:
        """Allocate the cycle's next member, linked from the one before. The first
        member's frame root holds the cycle until its lifetime ends."""
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
        # The next collection runs after the let-gos of its kB: the next automatic
        # one, or a full one the workload may call sooner.
        boundary = heap.next_collection()
        if self._next_full_collection is not None:
            full = self._next_full_collection()
            if full is not None:
                boundary = min(boundary, full)
        if ends <= boundary and not self._make_every_transient:
            heap.allocate_unseen()
            return
        x = heap.allocate()
        self._end_at(ends, x, 0)

    def _end_at(self, clock: int, x: int, leaves_unreachable: int) -> None:
        heap = self._heap
        let_go = partial(heap.let_go_frame_root, x, leaves_unreachable)
        self._let_gos.at(clock, let_go)


@dataclass(frozen=True)
class WorkloadParameters:
    """A workload: its background churn, its structures and its seed."""

    churn: ChurnParameters
    structures: tuple[StructureParameters, ...]
    seed: int
    # Whether the run ends as a worker does, in shutdown: its frames return, and
    # finalize_modules runs two full collections.
    shutdown: bool = False


class Workload:
    """A workload over a heap, one kB at a time: builds of its structures, and
    background churn between them.

    Structures without a rebuild interval build first, one after another, in the
    order the parameters list them, as a worker starts up. A repeating structure
    first falls due once they have built, and again each time its interval comes
    round from there. It waits for any build under way, so builds never overlap.
    A structure that asks for full collections gets one before each build
    and one after each drop, after the let-gos of the drop's kB."""

    def __init__(
        self,
        heap: Heap,
        parameters: WorkloadParameters,
        *,
        make_every_transient: bool = False,
    ) -> None:
        self._heap = heap
        self._structures = parameters.structures
        self._let_gos = LetGos()
        calls_collect = any(s.full_collections for s in self._structures)
        self._churn = Churn(
            heap,
            Random(parameters.seed),
            parameters.churn,
            make_every_transient=make_every_transient,
            let_gos=self._let_gos,
            next_full_collection=self._next_full_collection if calls_collect else None,
        )
        # The full collections that follow drops, by the clock of their kB.
        self._full_collections: dict[int, int] = {}
        # Each repeating structure's rebuild interval, and when it next falls due,
        # counted from the clock the others finish building at.
        self._intervals = {
            i: s.rebuild_interval
            for i, s in enumerate(self._structures)
            if s.rebuild_interval is not None
        }
        self._start: int | None = None
        self._due: dict[int, int] = {}
        # The structures waiting to build, in the order they fell due.
        self._waiting = [
            i for i, s in enumerate(self._structures) if s.rebuild_interval is None
        ]
        # The build under way, with its structure's index and its first kB.
        self._current: tuple[int, Build, int] | None = None
        self._builds: list[tuple[int, int, int]] = []
        # The churn allocations still to follow the last built object.
        self._churn_left = 0

    @property
    def builds(self) -> list[tuple[int, int, int]]:
        """Each finished build: its structure's index, its first kB and its last."""
        return list(self._builds)

    def run_to(self, clock: int) -> None:
        """Run the workload until the allocation clock reads `clock`."""
        heap = self._heap
        while heap.clock < clock:
            self._step()
            # Within each kB the clock moves, then the workload lets go of each
            # lifetime that ends there (ADR 0005), and calls `gc.collect()` after
            # each drop that asks for it.
            self._let_gos.run(heap.clock)
            for _ in range(self._full_collections.pop(heap.clock, 0)):
                heap.collect_full("full")

    def shut_down(self) -> None:
        """End as a worker does: its frames have returned, and finalize_modules lets
        go of the modules and runs two full collections."""
        heap = self._heap
        heap.let_go_every_frame_root()
        heap.let_go_of_the_modules()
        for _ in range(2):
            heap.collect_full("shutdown")

    def _step(self) -> None:
        """Make the kB's one allocation. With no build under way, the first
        structure waiting starts one. A build makes its next object, or churn makes
        the allocations that follow each built object; with no build, churn makes
        the allocation."""
        self._fall_due()
        if self._current is None and self._waiting:
            i = self._waiting.pop(0)
            if self._structures[i].full_collections:
                self._heap.collect_full("full")
            self._current = (
                i,
                Build(self._heap, self._structures[i]),
                self._heap.clock + 1,
            )
        if self._current is None:
            self._churn.step()
            return
        i, build, first_kb = self._current
        if self._churn_left:
            self._churn.step()
            self._churn_left -= 1
        else:
            build.add()
            self._churn_left = self._structures[i].build_churn
        if build.done and not self._churn_left:
            self._finish(i, build, first_kb)

    def _fall_due(self) -> None:
        """Queue each repeating structure that has fallen due. If its last build is
        still waiting or under way, skip this rebuild."""
        clock = self._heap.clock
        start = self._start
        if start is None:
            if self._waiting or self._current is not None:
                return
            self._start = start = clock
            self._due = dict.fromkeys(self._intervals, clock)
        building = None if self._current is None else self._current[0]
        for i, interval in self._intervals.items():
            if self._due[i] <= clock:
                if i != building and i not in self._waiting:
                    self._waiting.append(i)
                self._due[i] = start + ((clock - start) // interval + 1) * interval

    def _finish(self, i: int, build: Build, first_kb: int) -> None:
        clock = self._heap.clock
        self._builds.append((i, first_kb, clock))
        structure = self._structures[i]
        if structure.lifetime is not None:
            drop = clock + structure.lifetime
            self._let_gos.at(drop, build.drop)
            if structure.full_collections:
                calls = self._full_collections
                calls[drop] = calls.get(drop, 0) + 1
        self._current = None

    def _next_full_collection(self) -> int | None:
        """The earliest clock the workload could call `gc.collect()` at, as far as it
        can tell now, or None if it never calls it again. Erring early makes
        transients no collection sees, never misses one (ADR 0005)."""
        clock = self._heap.clock
        earliest = list(self._full_collections)
        for i, structure in enumerate(self._structures):
            if not structure.full_collections:
                continue
            # A waiting build could start at the next kB, and so could a repeating
            # structure's first once the others have built. A repeating structure's
            # next build starts no sooner than it falls due.
            if i in self._waiting or (self._start is None and i in self._intervals):
                earliest.append(clock)
            if i in self._due:
                earliest.append(self._due[i])
            # A build under way ends now or later, and its drop a lifetime after.
            building = self._current is not None and self._current[0] == i
            if building and structure.lifetime is not None:
                earliest.append(clock + structure.lifetime)
        return min(earliest, default=None)
