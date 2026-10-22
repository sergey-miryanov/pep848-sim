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

from pep848_sim.collector import (
    CollectionCounts,
    Collector,
    CollectorSettings,
    Space,
)


class IncrementalCollector(Collector):
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

    @override
    def add_module_root(self, x: int) -> None:
        """sys starts on reachable, as the pseudocode starts it."""
        self.reachable.append(x)

    @override
    def collect(self) -> None:
        self.young_collection() if self.young_next else self.old_collection()
        self.young_next = not self.young_next

    def young_collection(self) -> None:
        oldest = self.aging.pop()
        candidates = len(oldest)
        survivors = self.collect_cycles(oldest)
        self.work_to_do += len(survivors)
        self.visited_space.extend(survivors)
        self.aging.insert(0, self.nursery)
        self.nursery = Space(self)
        survived = len(survivors)
        self.counts.append(
            CollectionCounts("young", 0, survived, candidates - survived)
        )

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
        marked = survived = freed = 0
        while self.work_to_do > 0:
            if self.reachable:
                moved = self.scan_reachable(self.work_to_do)
                self.work_to_do -= moved
                marked += moved
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
                break  # the pseudocode returns; the counts below come first
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
            survived += len(survivors)
            freed += collected
        self.counts.append(CollectionCounts("old", marked, survived, freed))

    def form_transitive_closure(self, obj: int) -> list[int]:
        """An increment: obj, and every pending object it reaches through pending
        objects, each taken out of pending_space."""
        increment = [obj]
        for x in increment:
            for target in self._heap.references(x):
                if target in self.pending_space:
                    self.pending_space.remove(target)
                    increment.append(target)
        return increment
