"""A run: one workload by one collector under one set of collector settings, from
an empty heap to a run length on the allocation clock. It yields its records as it
goes, so that the widget can draw them (ADR 0006), and keeps its state in its
generator, none at module level (ADR 0007).
"""

from collections.abc import Callable, Iterator

from pep848_sim.collectors.collector import Collector, CollectorSettings, Record
from pep848_sim.collectors.heap import Heap
from pep848_sim.workload import Workload, WorkloadParameters


def run(
    parameters: WorkloadParameters,
    make_collector: Callable[[CollectorSettings], Collector],
    settings: CollectorSettings,
    run_length: int,
    every: int,
) -> Iterator[list[Record]]:
    """Run the workload under a collector that `make_collector`, such as a
    collector's class, makes from the settings. Yield the newest records each time
    `every` of them have built up, and the rest at the end."""
    collector = make_collector(settings)
    heap = Heap(collector)
    workload = Workload(heap, parameters)
    records = collector.records
    sent = 0
    while heap.clock < run_length:
        # One threshold0 at a time: a collection comes at the start of its first
        # allocation, so each adds one record at most.
        workload.run_to(min(heap.clock + settings.threshold0, run_length))
        if len(records) - sent >= every:
            yield records[sent:]
            sent = len(records)
    heap.collect_if_due()
    if len(records) > sent:
        yield records[sent:]
