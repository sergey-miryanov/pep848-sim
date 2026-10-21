# The widget leads with figures, then two columns of panels

The prototype for #9 drew the widget's panels three ways on records from
#8's simulator, up to 2000 collections a run, and the widget takes its layout
from two of them. A row of figures comes first, each legacy beside
incremental: peak work, peak uncollected garbage, work per MB, yield,
collections, and sweeps or gen 2 collections. Below it are two columns,
legacy on the left and incremental on the right, each with three panels
whose y-scales are shared across the columns: the heap by space, stacked,
with the reachable line on top, so that the gap between them is the
uncollected garbage; work, binned into about forty bins a run, each a whole
number of collection intervals, stacked as marked, survived and freed; and
the work budget, a step line with a bold zero line and the negative stretch
shaded, which the legacy column replaces with a line saying it keeps none.
The layout is for the desktop; the phone layout waits for the Guide
milestone. It is a starting point, chosen on records from a rough simulator:
once the real simulator's presets draw it, the layout is open to change, and
this record is amended when it does.

Work is binned because a bar per collection does not survive a long run: at
500 collections a bar is about a pixel wide, at 2000 a hairline, and its
three parts blur together. A single collection's peak lives in the figures.
The binned layout was also the cheapest to redraw. Plot rebuilds a chart on
every redraw, so the cost grows with the records, and this layout redrew
about 600 collections within a 60 Hz frame. While runs stream (ADR 0006),
the page draws whatever records have arrived, once an animation frame, and
each y-scale grows to the next of 1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6 and 8 times
a power of ten.

## Considered Options

- Both collectors overlaid on the same axes: the clearest comparison of the
  two heaps, but it drops the spaces, through which the guide explains the
  PEP.
- A bar per collection: readable only for short runs, and twice as slow to
  redraw.
- Summary tiles at the foot of each column as well: half their numbers
  repeat the figures.
