# Runs stream their records to the widget

A run takes 1.3 to 1.7 µs per kB it allocates under Pyodide, in the prototype
for #6, and some presets need long runs: with 100 MB of module globals, three
sweeps take over 1.2 GB on the allocation clock. Two such runs take seconds,
so a run in the browser's worker hands its records to the widget as it goes,
and the widget fills the charts in from the left. The allocation clock is
their x-axis, and the widget knows its end, the preset's run length, before
the run starts.

A run is a generator that yields its newest records every few collections.
The worker alternates the two runs, so their columns grow side by side, and
returns to its event loop after each yield, so the widget can cancel both
runs and start again when a reader changes a control. To return, the worker
posts a message on a `MessageChannel` it makes for that yield, and a message
from the page gets in between two parts within about 10 ms at the median, in
the prototype for #7. A nested `setTimeout(0)` would wait at least 4 ms a
yield, which there added about a second over the 144 parts of two runs of
1 GB. Interrupting Python inside a run would need cross-origin isolation,
whose headers GitHub Pages cannot send. The page redraws at most once an
animation frame, and its y-scales grow with the data. Alternating changes
nothing in either run, whose state stays in its own generator.

## Considered Options

- Cap a run's length to fit two runs in 1 s: presets with long sweeps would
  stop before they show three.
- Run to the end, then draw: simpler, but a long run shows the reader nothing
  for seconds.
