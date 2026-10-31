"""The incremental collector PEP 848 proposes, as the reference branch runs it
(ADR 0024): sergey-miryanov/cpython@incremental-gc-update-2, Python/gc.c.

The names are the PEP's pseudocode's. Each stands for a field of `struct
_gc_runtime_state` (Include/internal/pycore_interp_structs.h) on the branch:

    nursery         young.nursery
    aging           young.aging: young.aging_spaces of them, young.next the oldest
    pending_space   old[visited_space ^ 1]
    visited_space   old[visited_space]
    visited_index   visited_space, which of old[0] and old[1] is visited
    reachable       old[2], the worklist of objects known to be reachable from sys
    work_to_do      old_work
    young_next      next_gen
"""

import heapq
from collections.abc import Iterator
from typing import Literal, override

from pep848_sim.collectors.collector import (
    Collector,
    CollectorSettings,
    Constants,
    FullKind,
    Space,
)


class OldSpace(Space):
    """A space that also takes objects at its front, as the branch's
    gc_list_merge_front puts survivors at the head of a list. Each object keeps a
    place, and the space finds its first and last by their places."""

    def __init__(self, collector: Collector) -> None:
        super().__init__(collector)
        self._place: dict[int, int] = {}
        self._front = 0
        self._back = 0
        # Places and objects, the last first and the first first. An entry goes
        # stale when its object leaves or takes a new place; pop skips those.
        self._lasts: list[tuple[int, int]] = []
        self._firsts: list[tuple[int, int]] = []

    @override
    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self._objects, key=self._place.__getitem__))

    @override
    def append(self, x: int) -> None:
        self._back += 1
        self._put(x, self._back)

    def merge_front(self, objects: list[int]) -> None:
        """Put objects first, in their order, ahead of those already here."""
        for x in reversed(objects):
            self._front -= 1
            self._put(x, self._front)

    @override
    def pop(self, index: Literal[0, -1] = -1) -> int:
        entries = self._lasts if index == -1 else self._firsts
        while True:
            place, x = heapq.heappop(entries)
            place = -place if index == -1 else place
            if x in self._objects and self._place[x] == place:
                self._take_out(x)
                return x

    def _put(self, x: int, place: int) -> None:
        super().append(x)
        self._place[x] = place
        if len(self._lasts) > 2 * len(self._objects) + 64:
            self._compact()
        heapq.heappush(self._lasts, (-place, x))
        heapq.heappush(self._firsts, (place, x))

    def _compact(self) -> None:
        """Drop the stale entries."""
        live = [(self._place[x], x) for x in self._objects]
        self._place = {x: place for place, x in live}
        self._firsts = live
        self._lasts = [(-place, x) for place, x in live]
        heapq.heapify(self._firsts)
        heapq.heapify(self._lasts)


class IncrementalCollector(Collector):
    # reachable, sys and the marking worklist, counts in visited.
    SPACES = ("nursery", "aging", "pending", "visited")

    def __init__(
        self,
        settings: CollectorSettings | None = None,
        constants: Constants | None = None,
    ) -> None:
        super().__init__(settings, constants)
        # threshold1 counts half-spaces, two to an aging space. Below 1 it runs as
        # 1, as the reference branch's gc.set_threshold() clamps it.
        threshold1 = max(1, self.settings.threshold1)
        self.aging = [Space(self) for _ in range(-(-threshold1 // 2))]
        self.pending_space = OldSpace(self)
        self.visited_space = OldSpace(self)
        self.reachable = OldSpace(self)
        # Young objects carry old[0]'s tag. While visited is old[1], that is
        # pending's tag, so marking and increments take young objects too.
        self.visited_index = 0
        # The constants' initial budget, by default -100_000 real objects, in
        # simulated ones (ADR 0002).
        self.work_to_do = self.constants.simulated(self.constants.initial_work_budget)
        # The branch starts with a young collection, as the PEP's abstract has it.
        self.young_next = True
        # Sweeps ended, for the records: each swap of pending and visited ends one.
        self.sweeps = 0

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

    def is_pending(self, x: int) -> bool:
        """Whether x carries pending's tag: it sits in pending_space, or it is young
        while visited is old[1], as visit_pending_object reads the tag."""
        if x in self.pending_space:
            return True
        if not self.visited_index:
            return False
        space = self.space_of.get(x)
        return space is self.nursery or any(space is aging for aging in self.aging)

    def young_collection(self) -> None:
        """gc_collect_incremental_young: collect the oldest aging space, credit the
        budget with its survivors and put them at visited's front."""
        oldest = self.aging.pop()
        survivors = self.collect_cycles(oldest)
        self.work_to_do += len(survivors)
        self.visited_space.merge_front(survivors)
        self.aging.insert(0, self.nursery)
        self.nursery = Space(self)

    def scan_reachable(self, limit: int) -> int:
        """scan_reachable_space: move objects from the head of reachable to visited,
        and what each reaches with pending's tag to reachable's tail, until it has
        moved `limit` or reachable runs empty. They are reachable and cannot be
        garbage."""
        moved_to_visited = 0
        while self.reachable:
            root = self.reachable.pop(0)
            self.visited_space.append(root)
            moved_to_visited += 1
            for obj in self._heap.references(root):
                if self.is_pending(obj):
                    self.reachable.append(obj)
            if moved_to_visited >= limit:
                break
        return moved_to_visited

    def flip(self) -> None:
        """flip_incremental_old_spaces: pending and visited swap, which ends a
        sweep, and sys goes on reachable if it carries pending's tag."""
        self.pending_space, self.visited_space = (
            self.visited_space,
            self.pending_space,
        )
        self.visited_index ^= 1
        sys = self._heap.module_root
        if self.is_pending(sys):
            self.reachable.append(sys)
        self.sweeps += 1

    def old_collection(self) -> None:
        """gc_collect_incremental_old: collect an increment of the old generation.
        It marks and takes increments until it has done the budget's work, then
        settles the budget once."""
        if self.work_to_do <= 0:
            return
        if not self.pending_space and not self.reachable:
            self.flip()
        increment_size = 0
        collected = 0
        while increment_size < self.work_to_do and (
            self.reachable or self.pending_space
        ):
            if self.reachable:
                moved = self.scan_reachable(self.work_to_do)
                increment_size += moved
                # The one count collect_cycles cannot see.
                self.marked += moved
                continue
            # The increment starts at pending's last object.
            increment = self.form_transitive_closure(self.pending_space.pop())
            candidates = len(increment)
            increment_size += candidates
            survivors = self.collect_cycles(increment)
            collected += candidates - len(survivors)
            self.visited_space.merge_front(survivors)
        if increment_size:
            self.work_to_do -= increment_size
            # Freeing lots of objects means lots of cycle garbage, so the collector
            # sweeps the heap faster to keep it down.
            self.work_to_do += self.constants.freed_credit * collected
        if not self.pending_space and not self.reachable:
            self.flip()
            self.work_to_do = 0

    def full_collection(self) -> None:
        """Collect the whole heap, as `gc.collect()` does: the branch's
        gc_collect_incremental_full (ADR 0012). Every object joins pending, old
        ones first and the young generation after them in the order they entered.
        It moves what sys reaches to visited unexamined, then examines the rest and
        moves the survivors to visited too, which it leaves as old[1]. The work
        budget starts again from 0, and with pending empty the next old collection
        starts a new sweep."""
        pending = self.pending_space
        pending.extend(self.visited_space)
        pending.extend(self.reachable)
        for space in reversed(self.aging):
            pending.extend(space)
        pending.extend(self.nursery)
        self.visited_index = 1
        self.reachable.append(self._heap.module_root)
        self.marked += self.scan_reachable(len(self._heap))
        self.visited_space.extend(self.collect_cycles(pending))
        self.work_to_do = 0

    def form_transitive_closure(self, obj: int) -> Space:
        """expand_incremental_region: an increment of obj and every object with
        pending's tag it reaches through them, each taken out of its space. It holds
        them in a space of its own, as gc_collect_incremental_old does."""
        increment = Space(self)
        increment.append(obj)
        # The walk's order, since a space cannot grow while a loop iterates it.
        reached = [obj]
        for x in reached:
            for target in self._heap.references(x):
                if self.is_pending(target):
                    increment.append(target)
                    reached.append(target)
        return increment
