"""A run: one workload by one collector under one set of collector settings and
constants, from an empty heap to a run length on the allocation clock, and on
through shutdown if the workload asks for one. It yields its records as it goes,
so that the widget can draw them (ADR 0006), and keeps its state in its
generator, none at module level (ADR 0007).
"""

from collections.abc import Callable, Iterator

from pep848_sim.collectors.collector import (
    Collector,
    CollectorSettings,
    Constants,
    Record,
)
from pep848_sim.collectors.heap import Heap
from pep848_sim.workload import Workload, WorkloadParameters


def run(
    parameters: WorkloadParameters,
    make_collector: Callable[[CollectorSettings, Constants], Collector],
    settings: CollectorSettings,
    run_length: int,
    every: int,
    constants: Constants | None = None,
) -> Iterator[list[Record]]:
    """Run the workload under a collector that `make_collector`, such as a
    collector's class, makes from the settings and the constants, the defaults
    unless given, and end in shutdown if the workload asks. Yield the newest
    records `every` at a time as they build up, and the rest at the end."""
    collector = make_collector(settings, constants or Constants())
    heap = Heap(collector)
    workload = Workload(heap, parameters)
    records = collector.records
    sent = 0
    while heap.clock < run_length:
        # One threshold0 at a time: one automatic collection at most, and any full
        # collections the workload calls.
        workload.run_to(min(heap.clock + settings.threshold0, run_length))
        while len(records) - sent >= every:
            yield records[sent : sent + every]
            sent += every
    heap.collect_if_due()
    if parameters.shutdown:
        workload.shut_down()
    while len(records) > sent:
        yield records[sent : sent + every]
        sent += every
