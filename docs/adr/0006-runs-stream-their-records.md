# Runs stream their records to the widget

A run's cost grows with the kB it allocates, 1.3 to 1.7 µs per kB under
Pyodide in the prototype for #6, while the run length a preset needs does
not: with 100 MB of module globals, three sweeps take over 1.2 GB on the
allocation clock. Rather than cap run lengths so that two runs finish within
a second, a run, computed in the browser's worker, hands its records to the
widget as it goes, and the charts fill in from the left. The allocation clock
is their x-axis, and its end, the preset's run length, is known before the
run starts.

A run is a generator that yields its newest records every few collections.
The worker alternates the two runs, so their columns grow side by side, and
returns to its event loop after each yield, so a changed control can cancel
both runs and start again. It returns with a message on a `MessageChannel`
of that yield's own: a nested `setTimeout(0)` waits at least 4 ms, which in
the prototype for #7 cost about a second over the 144 parts of two runs of
1 GB, and a message from the page still ran between parts, within about
10 ms at the median. Interrupting Python inside a run would need
cross-origin isolation, whose headers GitHub Pages cannot send. The page
redraws at most once an animation frame, and its y-scales grow with the
data. Alternating changes nothing in either run, whose state stays in its own
generator.

## Considered Options

- Cap a run's length to fit two runs in 1 s: presets with long sweeps would
  stop before they show three.
- Run to the end, then draw: simpler, but a long run shows the reader nothing
  for seconds.
