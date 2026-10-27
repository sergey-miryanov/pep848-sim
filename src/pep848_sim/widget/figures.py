"""The row of figures a widget leads with (ADR 0008), from a run's records alone."""

from collections.abc import Iterable
from typing import NamedTuple, get_args

from pep848_sim.collectors.collector import FullKind, Record

# The kinds of a full collection's record, which `gc.collect()` or shutdown ran.
_FULL = get_args(FullKind.__value__)


class Figures(NamedTuple):
    """The figures of a run's records so far. `add` takes the records that come
    next, so the figures grow as the run streams (ADR 0006)."""

    # Of the collections the runtime started: a full collection takes the whole
    # heap in either collector by design (ADR 0012).
    peak_work: int = 0
    # As a collection starts, when it peaks (ADR 0010).
    peak_uncollected_garbage: int = 0
    # Idle ones included.
    collections: int = 0
    # The incremental run's; a legacy run has none.
    sweeps: int = 0
    # The legacy run's.
    gen2_collections: int = 0
    work: int = 0
    freed: int = 0
    survived: int = 0
    # kB, by the last collection.
    allocated: int = 0

    # The ratios divide int by int, which Python rounds correctly, so Pyodide
    # derives the same floats as CPython (ADR 0007).
    @property
    def work_per_mb(self) -> float:
        return self.work * 1000 / self.allocated

    @property
    def yield_(self) -> float | None:
        """None until the run has examined an object."""
        examined = self.freed + self.survived
        return self.freed / examined if examined else None

    def row(self) -> tuple[int, int, float, float | None, int, int, int]:
        """The figures in the order the widget shows them: what the worker sends
        the page."""
        return (
            self.peak_work,
            self.peak_uncollected_garbage,
            self.work_per_mb,
            self.yield_,
            self.collections,
            self.sweeps,
            self.gen2_collections,
        )

    def add(self, records: Iterable[Record]) -> Figures:
        figures = self
        for record in records:
            work = record.work
            uncollected = sum(record.spaces_before) - record.reachable_before
            automatic = record.kind not in _FULL
            peak_work = max(figures.peak_work, work) if automatic else figures.peak_work
            figures = Figures(
                peak_work=peak_work,
                peak_uncollected_garbage=max(
                    figures.peak_uncollected_garbage, uncollected
                ),
                collections=figures.collections + 1,
                sweeps=record.sweep,
                gen2_collections=figures.gen2_collections + (record.kind == "gen 2"),
                work=figures.work + work,
                freed=figures.freed + record.freed,
                survived=figures.survived + record.survived,
                allocated=record.clock,
            )
        return figures
