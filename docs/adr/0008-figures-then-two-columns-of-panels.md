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
We chose this layout as a starting point, on records from a rough simulator.
Once the widget draws the real simulator's presets, the layout is open to
change, and whoever changes it amends this record.

The layout began on the desktop, and the widget now fits a phone's width too
(#171). It lays out by its own width, since the playground's source takes a
third of a wide screen and leaves the widget the rest. The figures run six to a row, three
below 840 px and two below 420 px, each legacy beside incremental. Below
780 px the top row stacks: the select and the controls, the object graph, then
its legend. Below 700 px a chart beside another would keep less than about
220 px of plot, so the incremental column moves under the legacy one. The
crosshair still marks both columns at one clock, and a reader who scrolls to
the other column finds the same clock marked there. A tooltip with no
room on either side of its mark covers the mark. The guide's widget lays out
its own way (ADR 0020): beside the rail, a compact widget keeps both columns
side by side below 700 px, so a step's text stays near both, and on a phone a
narrow widget shows one collector at a time at the full width, through two
tabs, where two columns stood 166 px wide each.

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

The work panel's y-scale leaves shutdown's work out (#202). Each of shutdown's
full collections takes the whole heap, the first while the modules still hold
it, so in connected_components shutdown's bin holds 179K objects, where the
runtime's largest bin holds 28K. A scale that fit it left the runtime's own
bars in the bottom seventh of the panel. The panel cuts shutdown's bin at the
scale's end instead: the bar stops square there, two slanted gaps cross it
below the end, and the bin's whole work stands above it. Its tooltip gives
that work in full. The scale keeps the work of the workload's gc.collect()
calls, which make most of create_gc_cycles' work. If a run's only work is
shutdown's, the scale fits that.

Each panel reads its values under the pointer (#115). On the heap panel and
the work budget, a crosshair snaps to the collection nearest the pointer,
across all four of the heap's lanes, and a tooltip gives the heap before that
collection and after it, or the budget it left. On the work panel, an outline
marks the bar under the pointer, and a tooltip gives its work, the full
collections' apart from the runtime's own. The crosshair and the outline
follow the pointer at once, and the tooltip waits until the pointer has rested
350 ms, so a pointer crossing a panel leaves its plot in view (#143). A move of
more than 3 px hides the tooltip again, and so does Escape. Both runs share
the allocation clock, so the pointer marks it in every panel of both columns,
and once it rests, the panel under it shows its tooltip in both, legacy beside
incremental at the same point in the same allocations (#116). The widget draws
the crosshair, the outline and the tooltip in an overlay of its own above
Plot's charts, and keeps where the pointer rests. A pointer move redraws no
chart: marking every panel of both columns took about 0.5 ms at 1,028
collections. Each redraw while runs stream draws the overlay again from the
records so far, so the tooltip holds and its values follow the run.

A reader can read the panels from the keyboard too (#141). They tab to each
panel with a tooltip, five in all, as the legacy column has no budget, and a
focused panel shows a ring in the text color. On the heap and the budget, the
arrow keys step to the collection before or after; on the work panel, to the
bin before or after. Home and End go to the first and the last, and up and
down step as on any slider. A bin reads at the clock that ends it, where the
collection that closed it ran. A collection's clock reads the bin that holds
its work, so the outline and the crosshairs mark the same collection. The keys
move the same clock as the pointer, so they mark every panel of both columns,
and the focused panel shows its tooltip in both at once. Escape hides it until
the next key. A panel that takes focus starts at the clock the keys last read
or the pointer last rested on, in any panel, or else at its first collection
or bin, so Tab carries the clock from panel to panel. Leaving the panel hides
the marks. A click focuses a panel as well, but the pointer reads it then, and
its marks go when the pointer leaves.

A screen reader takes each panel for a slider along the allocation clock,
named by its column's heading and its caption. Its value is the tooltip's
readout as one sentence: "gen 0 collection at 6 MB, in MB, before and after:
heap 6.00, 6.00; reachable 6.00, 6.00; …". The widget sets the value on focus
and at each key, and leaves it alone when a redraw or the pointer moves the
marks, so a screen reader says nothing while runs stream or the pointer moves.
The slider's role also hands the arrow keys to the panel, which in a screen
reader's browse mode would read the page instead.

Beside the select and the controls, the widget draws a sample of the
request's object graph (#151): a few objects of each structure, linked as its
shape links them, under sys or the frame that holds it, with each link that
lies on a cycle in the freed color. connected_components' graph alone holds
89,007 objects, so the sample keeps the first children of each object, as far
as each shape needs to show itself: four chains three objects deep, a binary
tree four levels deep, six children of six children for a hierarchy or a
graph's nodes, and ten rings. A force layout places the sample with sys and
the frames pinned along the top, and fits it into its frame. The objects keep
to ink, and a number on each structure's first object points to its line in
the legend under the controls, since the panels below take all eight of the
palette's hues. The graph moves the figures down about 150 px. On the
playground the legend edits the workload (ADR 0013). A compact widget, as the
guide's, leaves out the graph and its legend, so that its charts come up
beside a step's text (ADR 0020).

## Considered Options

- Both collectors overlaid on the same axes: the clearest comparison of the
  two heaps, but it drops the spaces, through which the guide explains the
  PEP.
- A bar per collection: readable only for short runs, and twice as slow to
  redraw.
- A work scale that fit the runtime's own collections alone, as #202 first
  proposed: create_gc_cycles' start-up collections would set it at 400
  objects, and the panel would cut every bar of its gc.collect() calls.
- A flat gap across a cut bar: the gaps between a bar's parts are flat, so it
  would read as one more part's edge.
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
- One collector at a time behind a switch on a phone: a reader compares the
  two runs at one clock, and a switch would hide one of them.
- Widths taken from the window: beside the playground's source, the widget
  would lay out for the whole screen and overflow its share of it.
- Plot's pointer and tip marks in each chart: each pointer move would rebuild
  every chart, 20 to 65 ms at 600 to 2,000 collections, and Plot's pointer
  reads one chart, where the heap panel is four.
- Hover only once both runs finish: the tooltip would go for the seconds each
  run takes after every slider release.
- A crosshair at the pointer's own clock: between two collections it would
  read the straight line drawn between their records, a value no record holds.
- The tooltip at once, as #115 first drew it: it covered the plot while the
  pointer crossed it.
- The values in each panel's legend row, with no tooltip: the plot stayed
  clear, but each legend had to keep two lines' height so its readings never
  pushed the charts under the pointer, and the readings shifted sideways as
  their widths changed. A prototype on the `prototype/hover-readout` branch
  compared it with the rest delay and the tooltip at once.
- A tooltip only while a key is held: no reader would find it, and touch has
  no keys.
- The crosshair alone in the column the pointer is not in: comparing the two
  runs at one clock would take a move to the other column and back.
- A live region that says each step aloud: in browse mode a screen reader
  keeps the arrow keys for reading the page, and a panel without a widget's
  role would not get them.
- A clock for each panel, from its first collection: a reader who tabbed from
  the legacy heap to the incremental heap would lose the point they compared.
- The work panel reading a clock in the bin that starts there, as the pointer
  first did: a collection at a bin's end would read the bin after its work,
  and a step on the heap would outline the wrong bar.
- A small diagram for each structure, laid out level by level under the
  controls: it showed each shape, but read as a strip of thumbnails
  that ran past the widget's edge.
- A graph for each preset after its paragraph under "The workloads": the
  reader had to scroll from the widget down to it and back.
- A row for each structure, its sample beside its builds and lifetimes on the
  allocation clock: it showed when each structure lives, but shrank each
  sample to a glyph.
- The graph under the controls with its legend beside it: it moved the
  figures down twice as far. A prototype on the `prototype/object-graph`
  branch compared these with the graph beside the controls.
- A hue for each structure, as the prototype drew them: its hues were the
  nursery's and the aging generation's in the panels below.
