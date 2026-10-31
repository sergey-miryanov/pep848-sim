# connected_components' graph takes its links from amazon0302

With the collector following the branch (ADR 0024), connected_components
still took one increment at 56 MB, of 295,696 real objects. Its workers take
two. At 48 MB an increment from `_node` examines 85,797 real objects: `_node`
and the attribute dicts it holds. At 60 MB one from `_adj` examines 231,870
and drives the budget to -191,565. The young collections after it examine
6,600 to 13,600 each, and at 96 MB an old collection takes the last 153
pending objects and ends the sweep. The preset's Graph shape could make none
of this. An instrumented worker on the reference build shows four reasons:

- networkx 3.4.2's Graph sets `_node` and `_adj` through data descriptors that
  write `G.__dict__`, so the dict comes into being after `G.graph` and
  `G._node`. The order runs G, `graph`, `_node`, `G.__dict__`, the cache,
  `_adj`, and `G.__dict__` takes `graph` and `_node` over from G.
- `move_unreachable` moves an object it scans with no outside references to
  the unreachable list. When an object it scans later reaches that one, it
  appends it to the young list's tail. The branch's survivors keep that order,
  and pending pops from its tail. When G first enters the old generation,
  `graph`, `_node` and that batch's attribute dicts move to the batch's tail,
  and `_adj` stays in place. So `_node`'s increment comes first.
- read_adjlist reads the file's edges in order, and each edge's data dict hangs
  off both endpoints' adjacency dicts, which the file spreads across the whole
  graph. Graph's edges reached back by a formula.
- read_adjlist's frame holds the file and its generator of lines, 153 real
  objects older than G. They stay pending after `_adj`'s increment.

The graph now takes its links from the file. A new shape, Amazon0302, holds
the six objects networkx makes first, then one object for every 16 real ones
read_adjlist makes (ADR 0002): an adjacency dict, which `_adj` holds; an
attribute dict, which `_node` holds; or an edge's data dict, which the objects
standing for its endpoints' adjacency dicts hold. `tools/amazon0302.py` reads
pyperformance's `amazon0302.txt.gz` and writes the table to
`src/pep848_sim/amazon0302.links`, 219 kB of zlib, which ships in `sim.zip`.
A larger structure repeats the table.

A shape can now take links back: a build drops the pairs a shape's `unlinks`
gives after it adds an object's links. Amazon0302 alone has them, for
`G.__dict__`'s hand-over. `collect_cycles` returns its survivors in the order
`move_unreachable` leaves them, which ADR 0024 now says. connected_components
gains a structure for read_adjlist's reader: 10 objects in a chain, which the
frame holds for as long as the graph takes to load.

Two trees stand for the cycles networkx's `argmap` decorators leave when they
compile a function's wrapper on its first call: closures that reach themselves
through their cells, with a Signature and its Parameters. One, of 8 objects,
builds as the load starts, for read_adjlist's and `empty_graph`'s wrappers. The
other, of 2, builds as the walks start, for `connected_components`' own. The
workers' young collections free 133 and 32 real objects there, at 38 and 146
MB, and an instrumented worker with `gc.DEBUG_SAVEALL` names them.

The Graph shape stays, for the playground and the links that name it.

## Consequences

connected_components' incremental columns on the presets page now fit its
workers' budget, examined and work to within 1%:

| Series | Before | After |
|---|---|---|
| gen 1 budget | 15% | 1% |
| gen 0 budget | 13% | 0% |
| gen 1 examined | 8% | 0% |
| gen 1 work | 8% | 0% |
| gen 0 examined | 5% | 1% |

Its increments come at 48 MB, 85,568 real objects, and at 60 MB, 228,528,
with the budget at -189,504. The sweep ends at 96 MB on 208. The wrappers'
cycles take gen 0's freed and yield from 4% to 2% under the incremental
collector, and under the legacy one freed from 2% to 1% and yield from 4% to
2%. Its legacy columns keep their other errors, and the other presets keep
their records.

The reader takes structure 8, and the graph moves from 7 to 9, behind the
cycles networkx's wrappers leave as the load starts. A link that resizes
`workload.structures.7` now resizes those cycles. The guide's large-increment
chapter points at 9, and its steps on connected_components give the new
increments.

## Considered Options

- Draw the edges' holders from a fitted distribution: a third of the edges
  hang off the newest node, the rest off nodes an exponential distance back,
  with means of 100,000 and 230,000 real objects. It put `_adj`'s increment at
  64 MB, against the workers' 60.
- Read `amazon0302.txt.gz` itself in the page's worker. It weighs 4.7 MB, and
  each run would parse 900,000 edges to keep one in 16.
- Change the Graph shape to networkx's. Readers' shapes and links that name
  Graph would change under them.
