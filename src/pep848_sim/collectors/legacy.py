"""The three-generation collector that the reference branch keeps behind
`-X gc=legacy` (ADR 0004), written as Python/gc.c on
sergey-miryanov/cpython@incremental-gc-update-2 does it.

Each name stands for a field of `struct _gc_runtime_state`:

    nursery              young.nursery
    aging                young.aging[0], the legacy collector's one aging space
    old                  old[0].head
    count0, count1       old[0].count and old[1].count, whose thresholds are
                         threshold1 and threshold2
    long_lived_pending   long_lived_pending
    long_lived_total     long_lived_total
"""

import math
from typing import override

from pep848_sim.collectors.collector import (
    Collector,
    CollectorSettings,
    Constants,
    FullKind,
    Space,
)


class LegacyCollector(Collector):
    SPACES = ("nursery", "aging", "old")

    def __init__(
        self,
        settings: CollectorSettings | None = None,
        constants: Constants | None = None,
    ) -> None:
        super().__init__(settings, constants)
        self.aging = Space(self)
        self.old = Space(self)
        # Gen 0 collections since the last gen 1 or 2, and gen 1 collections since
        # the last gen 2.
        self.count0 = 0
        self.count1 = 0
        # Objects that survived gen 1 collections since the last gen 2, and those
        # the last gen 2 left.
        self.long_lived_pending = 0
        self.long_lived_total = 0

    @override
    def space_sizes(self) -> tuple[int, ...]:
        return (*super().space_sizes(), len(self.aging), len(self.old))

    @override
    def collect(self) -> None:
        """Collect the generation that select_generation picks, as the branch's
        gc_collect_main does under -X gc=legacy."""
        collections = (
            self.collect_generation0,
            self.collect_generation1,
            self.collect_generation2,
        )
        generation = self.select_generation()
        with self.recording(f"gen {generation}"):
            collections[generation]()

    @override
    def collect_full(self, kind: FullKind) -> None:
        """A gen 2 collection, as gc_collect_main runs one for `gc.collect()`."""
        with self.recording(kind):
            self.collect_generation2()

    def select_generation(self) -> int:
        """gc_select_generation, as the legacy collector reads it: the oldest
        generation whose count is over its threshold. Gen 2 waits until the objects
        awaiting it reach the long-lived ratio, a quarter unless the constants say
        otherwise, of those the last gen 2 left."""
        counts = (self.count0, self.count1)
        thresholds = (self.settings.threshold1, self.settings.threshold2)
        # Rounded down, as C divides the branch's long_lived_total / 4.
        waiting = math.floor(self.long_lived_total * self.constants.long_lived_ratio)
        for i in (1, 0):
            if counts[i] <= thresholds[i]:
                continue
            if i == 1 and self.long_lived_pending < waiting:
                continue
            return i + 1
        return 0

    def collect_generation0(self) -> None:
        """gc_collect_legacy_generation0: the nursery, into aging."""
        self.count0 += 1
        survivors = self.collect_cycles(self.nursery)
        self.aging.extend(survivors)

    def collect_generation1(self) -> None:
        """gc_collect_legacy_generation1: the nursery and aging, into old."""
        self.count0 = 0
        self.count1 += 1
        self.aging.extend(self.nursery)
        survivors = self.collect_cycles(self.aging)
        self.old.extend(survivors)
        self.long_lived_pending += len(survivors)

    def collect_generation2(self) -> None:
        """gc_collect_legacy_generation2: the whole heap, collected in old."""
        self.count0 = 0
        self.count1 = 0
        self.old.extend(self.nursery)
        self.old.extend(self.aging)
        survivors = self.collect_cycles(self.old)
        self.long_lived_pending = 0
        self.long_lived_total = len(survivors)
