# A preset takes its shapes from the benchmark's code and its lengths from gcmon's records

A preset models one worker of its benchmark, from interpreter start-up to
shutdown, since the collector sees all of it: the imports, the benchmark's
loops, pyperf's own work, and the full collections the interpreter runs as it
shuts down. We take its workload parameters from two sources and fit the rest
by hand.

From the benchmark's code we take the shapes and the roots, which objects form
cycles and how large, what lives for one loop or for the whole worker, where
`gc.collect()` runs, and how many real objects each part makes. We divide
those counts by 16, as ADR 0002 has it.

From gcmon's records of the worker's collections (#117) we take lengths on the
allocation clock. The reference branch takes each new real object's size off a
budget of `threshold0` kB, every collection resets the budget, and the next
automatic collection comes when it runs out: the rule the simulator's clock
follows. Each automatic collection marks `threshold0` kB, so a loop that spans
n of them allocates n × `threshold0` kB. `gc.collect()` resets the budget too.
A loop that allocates less than `threshold0` kB between two calls leaves no
automatic collection to count, so we take its length from the code's counts.

A preset runs for its worker's own length on the clock: start-up, the
benchmark's loops as many times as the records show, and shutdown. The loops
begin as start-up ends: a repeating structure counts its interval from there,
so its first build starts the first loop, whatever start-up's length. Where the
loops leave no count in the records, as json_loads' calls leave none, the
worker's automatic collections give its length: it ends within `threshold0` kB
of the last one, and the preset ends halfway. A target of
so many sweeps fails for a benchmark that calls `gc.collect()` more often than
every `threshold0` kB, as create_gc_cycles does. Each call resets the budget,
so no automatic collection comes during its loops, and no sweep ends.

Some parameters neither source fixes, such as the start-up heap's shape or the
churn inside a library. The five benchmarks' workers start up alike: in #117's
rerun, their first two collections agree within 5%. Their presets share one
start-up of four structures. Under the module root hang a tree, which shutdown
leaves as cyclic garbage, and chains, which refcounting frees. Shutdown's
collections set no target: gcmon reads a worker once a tick, and a worker can
exit before gcmon reads them (#117). Where gcmon caught `finalize_modules`'
first collection, what it frees sizes the tree. Under a frame root hang chains
for the objects sys does not reach, which the branch's full collections
examine and keep while they mark the rest. A tree that start-up lets go of as
soon as it is built gives its first collections the cyclic garbage they free.

The objects a worker's first collection examines under the legacy collector
set start-up's size, where the heap that collection reads would count more. A
collection untracks a tuple that holds only objects it never sees, without
examining it, and by start-up's end a third of its heap has gone that way. The
simulator has no untracking, and the PEP's pseudocode has none (ADR 0003), so
start-up's build churn takes in those tuples: they move the allocation clock,
and leave the heap before a collection sees them. The branch's incremental
collector examines nothing at start-up, and keeps them tracked until a
collection examines them: a json_loads worker's heap holds 29,700 real objects
all run, where its preset's holds about 18,300.

A script in `tools/` prints beside its benchmark's a preset's collections, the
objects one of them examines on average, their yields, and the objects its
first collection examines. We change the open
parameters until the two agree within #117's tolerance, a fifth of the
benchmark's yield or half a point, whichever is wider, and leave the rest as
the code and the records set them. Each parameter's comment names its source:
the code, at the pyperformance version #117's metadata records, or the record
we fitted it to.

## Considered Options

- Measure the object graph with a `gc.callbacks` hook in each worker that
  walks `gc.get_objects()` and `gc.get_referents()` now and then. It needs a
  gcmon feature and a separate slow run, for precision a fitted preset throws
  away. It cannot see the objects refcounting frees, and the benchmarks are
  short scripts whose code shows what they build.
- tracemalloc: it counts bytes by allocation site and records no references
  between objects, so it shows no shapes.
- A tolerance from how far a benchmark's workers spread: they agree to within
  0.01 points, so it would ask a coarse model for an exact fit.
- A tolerance of 5 points, the placeholder before the rerun: wider than every
  target but one, it would pass a preset that finds no garbage against a
  benchmark whose collections find 1.4%.
- A share of the benchmark's yield alone: most targets sit at 0.05% or under,
  where a share of them leaves a preset no room.
- An optimiser over the workload parameters: a preset leaves few of them open,
  a run takes seconds, and a fit by hand keeps a reason for each number.
- About three sweeps for every preset, as CONTEXT.md first had it:
  create_gc_cycles never ends one.
- A start-up structure with a fitted share of cycles of its own: it needs a
  new shape, where two structures need none.
- Start-up's size from the heap its first collection reads, as this record
  first had it. The heap counts the tuples that collection untracks, so a
  preset's start-up would hold about 29,500 real objects where its benchmark's
  collections examine about 18,300. create_gc_cycles' `gc.collect()` calls
  would find 3.4% cyclic garbage where its benchmark's find 5.4%.
- Untracking in the simulator: a share of each structure that a collection
  untracks without examining it. It needs a workload parameter, and a step the
  PEP's pseudocode does not have (ADR 0003).
- A start-up for each preset: the five agree within 5% through their second
  collection, and past it the records cannot tell start-up from the
  benchmark's own work.
- Start-up's cyclic garbage from the churn: the churn's parameters hold for
  the whole run, and json_loads' loops make no cycles.
- Repeating structures that count their intervals from the run's start, with a
  start-up that fills whole intervals, as create_gc_cycles' does:
  xml_etree_parse's values run 25 MB each, and no start-up fills a whole
  number of them. An offset for each repeating structure would add a workload
  parameter for every request to spell out.
