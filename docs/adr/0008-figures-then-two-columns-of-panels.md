# The widget leads with figures, then two columns of panels

The prototype for #9 drew the widget's panels three ways on records from
#8's simulator, up to 2000 collections a run, and the widget takes its layout
from two of them. A row of figures comes first, each legacy beside
incremental: peak work, peak uncollected garbage, work per MB, yield,
collections, and sweeps or gen 2 collections. Below it are two columns,
legacy on the left and incremental on the right, each with three panels
whose y-scales the two columns share: the heap by space, in lanes on one
allocation clock; work, binned into about forty bins a run, each a whole
number of collection intervals, stacked as marked, survived and freed; and
the work budget, a step line with a bold zero line and the negative stretch
shaded, which the legacy column replaces with a line saying it keeps none.
The layout is for the desktop, and the Guide milestone takes up the phone
layout. We chose this layout as a starting point, on records from a rough
simulator. Once the widget draws the real simulator's presets, the layout is
open to change, and whoever changes it amends this record.

The heap panel's top lane draws the whole heap and its reachable part, and
shades the gap between them, the uncollected garbage. Below it, the nursery,
the aging generation and the old generation each get a lane, a line over a
light fill. In the incremental column the old generation's lane stacks the
pending space and the visited space as fills alone: together they make the old
generation, and the edge between them shows how far the sweep got. Every lane
in both columns has the same height and one y-scale, so a height reads as the
same MB in any lane, and the nursery's lane shows how little of the heap it
holds. Only the top lane's axis names the unit, and the lanes' colors and the
legend name what each shows. The panel first stacked every space, the old
generation at the bottom, with a line along each band's top. Each line traced
its band and every band below it, so the nursery's, at the top, climbed with
the whole heap, though each gen 0 or young collection empties the nursery
(#110).

The widget bins work because a bar per collection turns unreadable in a long
run: at 500 collections a bar is about a pixel wide, at 2000 a hairline, and
its three parts blur together. The figures carry a single collection's peak.
The binned layout redrew fastest of the three variants. Plot rebuilds a chart
on every redraw, so the cost grows with the records, and the prototype's
layout fit about 600 collections in a 60 Hz frame. Splitting the heap panel
into lanes cost a little. We timed both on one machine: a redraw took about 20
ms against 18 ms at 600 collections, and 50 to 65 ms either way at 2000. While
runs stream (ADR 0006), the page draws whatever records have arrived, once an
animation frame, and each y-scale grows to the next of 1, 1.2, 1.5, 2, 2.5, 3,
4, 5, 6 and 8 times a power of ten.

## Considered Options

- Both collectors overlaid on the same axes: the clearest comparison of the
  two heaps, but it drops the spaces, through which the guide explains the
  PEP.
- A bar per collection: readable only for short runs, and twice as slow to
  redraw.
- Summary tiles at the foot of each column as well: half their numbers
  repeat the figures.
- The heap stacked by space, as the panel first drew it: each band's line
  traced the bands below it too, and the nursery's traced the whole heap.
- The same stack with the nursery at the bottom: its line traced the nursery
  alone, and the top band's line traced the whole heap instead.
- A line per space on one set of axes: the nursery's and the aging
  generation's tangled near zero, under the old generation's.
- Lanes with a y-scale each: the nursery's sawtooth filled its lane, but the
  same height read as 4 MB in one lane and 60 MB in another.
