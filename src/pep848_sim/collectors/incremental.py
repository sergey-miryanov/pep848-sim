"""The incremental collector PEP 848 proposes, written as its pseudocode reads.

The names are the pseudocode's. Each stands for a field of `struct
_gc_runtime_state` (Include/internal/pycore_interp_structs.h) on the reference
branch, sergey-miryanov/cpython@incremental-gc-update-2:

    nursery         young.nursery
    aging           young.aging: young.aging_spaces of them, young.next the oldest
    pending_space   old[visited_space ^ 1]
    visited_space   old[visited_space]
    reachable       old[2], the worklist of objects known to be reachable from sys
    work_to_do      old_work, which the branch settles once per old collection
                    where the pseudocode settles it after each increment (ADR 0003)
    young_next      next_gen
"""

from typing import override

from pep848_sim.collectors.collector import (
    Collector,
    CollectorSettings,
    FullKind,
    Space,
)


class IncrementalCollector(Collector):
    # reachable, sys and the marking worklist, counts in visited.
    SPACES = ("nursery", "aging", "pending", "visited")

    def __init__(self, settings: CollectorSettings | None = None) -> None:
        super().__init__(settings)
        # threshold1 counts half-spaces, two to an aging space.
        self.aging = [Space(self) for _ in range(-(-self.settings.threshold1 // 2))]
        self.pending_space = Space(self)
        self.visited_space = Space(self)
        self.reachable = Space(self)
        # The pseudocode's -100_000 real objects, 16 to a simulated one (ADR 0002).
        self.work_to_do = -100_000 // 16
        self.young_next = False
        # Sweeps ended, for the records.
        self.sweeps = 0

    @override
    def add_module_root(self, x: int) -> None:
        """sys starts on reachable, as the pseudocode starts it."""
        self.reachable.append(x)

    @override
    def space_sizes(self) -> tuple[int, ...]:
        return (
            *super().space_sizes(),
            sum(len(space) for space in self.aging),
            len(self.pending_space),
            len(self.visited_space) + len(self.reachable),
        )

    @override
    def budget(self) -> int:
        return self.work_to_do

    @override
    def sweep(self) -> int:
        return self.sweeps

    @override
    def collect(self) -> None:
        with self.recording("young" if self.young_next else "old"):
            self.young_collection() if self.young_next else self.old_collection()
            self.young_next = not self.young_next

    @override
    def collect_full(self, kind: FullKind) -> None:
        with self.recording(kind):
            self.full_collection()

    def young_collection(self) -> None:
        oldest = self.aging.pop()
        survivors = self.collect_cycles(oldest)
        self.work_to_do += len(survivors)
        self.visited_space.extend(survivors)
        self.aging.insert(0, self.nursery)
        self.nursery = Space(self)

    def scan_reachable(self, limit: int) -> int:
        """Move some reachable objects from pending to reachable and from
        reachable to visited. They are reachable and cannot be garbage."""
        moved_to_visited = 0
        while self.reachable and moved_to_visited < limit:
            root = self.reachable.pop()
            self.visited_space.append(root)
            moved_to_visited += 1
            for obj in self._heap.references(root):
                if obj in self.pending_space:
                    self.pending_space.remove(obj)
                    self.reachable.append(obj)
        return moved_to_visited

    def old_collection(self) -> None:
        """Collect an increment of the old generation."""
        while self.work_to_do > 0:
            if self.reachable:
                moved = self.scan_reachable(self.work_to_do)
                self.work_to_do -= moved
                # The one count collect_cycles cannot see.
                self.marked += moved
                continue
            if not self.pending_space:
                self.pending_space, self.visited_space = (
                    self.visited_space,
                    self.pending_space,
                )
                # The pseudocode's visited.remove(sys): after the swap, sys sits in
                # pending_space.
                sys = self._heap.module_root
                self.pending_space.remove(sys)
                self.reachable.append(sys)
                self.work_to_do = 0
                self.sweeps += 1
                return
            obj = self.pending_space.pop(0)
            # form transitive closure starting at obj, taking objects from pending
            increment = self.form_transitive_closure(obj)
            candidates = len(increment)
            self.work_to_do -= candidates
            survivors = self.collect_cycles(increment)
            collected = candidates - len(survivors)
            self.visited_space.extend(survivors)
            # If we are collecting lots of objects, that means there is a lot of
            # cycle garbage and we should sweep the heap faster to keep the amount
            # of garbage down
            self.work_to_do += 2 * collected

    def full_collection(self) -> None:
        """Collect the whole heap, as `gc.collect()` does. The PEP gives it no
        pseudocode, so it follows the branch's gc_collect_incremental_full (ADR 0012).
        Every object joins pending, old ones first and the young generation after them
        in the order they entered. What sys reaches moves to visited unexamined, and
        the rest is examined, its survivors joining visited. The work budget starts
        again from 0, and with pending empty the next old collection starts a new
        sweep."""
        pending = self.pending_space
        pending.extend(self.visited_space)
        pending.extend(self.reachable)
        for space in reversed(self.aging):
            pending.extend(space)
        pending.extend(self.nursery)
        self.reachable.append(self._heap.module_root)
        self.marked += self.scan_reachable(len(self._heap))
        self.visited_space.extend(self.collect_cycles(pending))
        self.work_to_do = 0

    def form_transitive_closure(self, obj: int) -> Space:
        """An increment: obj, and every pending object it reaches through pending
        objects, each taken out of pending_space. It holds them in a space of its
        own, as the branch's gc_collect_incremental_old does."""
        increment = Space(self)
        increment.append(obj)
        # The walk's order, since a space cannot grow while it is iterated.
        reached = [obj]
        for x in reached:
            for target in self._heap.references(x):
                if target in self.pending_space:
                    increment.append(target)
                    reached.append(target)
        return increment
