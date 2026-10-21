# The widget runs a Python simulator of the PEP's algorithm

The reference implementation of PEP 848 builds for Emscripten, so the widget
could have run the real collector in the browser. We chose a small Python
simulator that models the PEP's algorithm on synthetic objects, and Pyodide
runs it in the browser through WASM. The real build would cost a 10-20 MB
download, a re-run of real Python on every slider move, a fresh interpreter
to switch collectors, and pause times that measure WASM speed through a
5-100 µs browser clock. The Go GC guide's widgets, the model for this one,
are cost-model simulations for the same reasons.

## Considered Options

- Real collector, plotted in wall time.
- Real collector, plotted in deterministic units (kB allocated, objects
  scanned) so every viewer sees the same chart.
- Aggregate model of counts per space, with no object graph. We rejected it:
  increment size decides old-generation pauses, and a model needs an object
  graph to produce it.
