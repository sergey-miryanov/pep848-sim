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
automatic collection to count, so we took its length from the code's counts.
From revision b8d8db86a4c on, each record carries `allocated`, the bytes the
worker had allocated that way as the collection started (#267). We read
lengths from it, between any two collections, explicit ones included. A
loop's real objects can outweigh ADR 0002's 64 B, as create_gc_cycles' nodes
do at 88 B: its structures keep the count of objects its collections examine,
and churn makes up the kB the loop allocates past them (#268).

A preset runs for its worker's own length on the clock: start-up, the
benchmark's loops as many times as the records show, and shutdown. The loops
begin once the structures that build once have built: a repeating structure
counts its interval from there, so its first build starts the first loop,
whatever start-up's length. A worker that allocates more before its loops, as
create_gc_cycles' workers do up to their first `gc.collect()` at 5,484 kB,
gets a structure that builds once after start-up and ends where the records
start the loops. Refcounting frees it as it ends, or later if the records'
collections still find it: async_tree_io_tg's fourth finds it, and so does its
gen 2 collection, so it stays to shutdown (#278, #279). The worker's automatic
collections give its length if the loops leave no count in the records, as
json_loads' calls leave none: it ends within
`threshold0` kB of the last one, and the preset ends halfway. A length set by a
count of sweeps would fail for a benchmark that calls `gc.collect()` more often
than every `threshold0` kB, as create_gc_cycles does: each call resets the
budget, so no automatic collection comes during its loops, and no sweep ends.

pyperf calibrates each run's loops on that run's timings, so a benchmark's
workers can run for different lengths under the two collectors. In the trace
at b8d8db86a4c, json_loads' workers made 10 automatic collections under the
incremental collector and 17 under the legacy one. A preset keeps one length,
since a widget runs both collectors on one workload, and follows the
incremental workers'. The yield test and `just compare` count only the
workers' collections that start within the kB the preset's run allocates.

Some workload parameters neither source fixes, such as the start-up heap's
shape or the churn inside a library. The five benchmarks' workers start up
alike: in #117's rerun, their first collections agree within 5%. Their presets
share one start-up of six structures. Under the module root hang a tree, which
shutdown leaves as cyclic garbage, and chains, which refcounting frees.
Shutdown's collections set no target: gcmon reads a worker once a tick, and a
worker can end before gcmon reads them (#117). The tree's size comes from what
`finalize_modules`' first collection frees, in the workers where gcmon caught
it. Under a frame root hang chains for the objects sys does not reach,
which the branch's full collections examine where they mark the rest. Start-up
lets go of two small trees as soon as it builds them, which give its first two
collections the cyclic garbage they free (#260). The first comes before the
module root's structures and the second just after the first collection, so
the second collection finds it young.

Start-up allocates more kB to an object once its first collection has come.
The workers' first collection examines 8,141 to 8,845 real objects at 2,000
kB, and their second 5,658 to 6,352 (#278). Start-up takes two build churns,
one up to the first collection and one past it, and the tree under the module
root builds in two parts, one at each. connected_components' second collection
examines 5,658, where the other four benchmarks' examine 5,855 to 6,352, and no
churn puts a collection within 5% of both. Its preset takes a late churn of
its own, and the other four share one.

The objects a worker's first collection examines under the legacy collector
set start-up's size, where the heap that collection reads would count more. A
collection untracks a tuple that holds only objects it never sees, without
examining it, and by start-up's end a third of its heap has gone that way. The
simulator has no untracking, and the PEP's pseudocode has none, so
start-up's build churns take in those tuples: they move the allocation clock,
and leave the heap before a collection sees them. The branch's incremental
collector examines nothing at start-up, and keeps them tracked until a
collection examines them: a json_loads worker's heap holds 29,700 real objects
all run, where its preset's holds about 18,500.

A script in `tools/` prints beside its benchmark's a preset's collections, the
objects one of them examines on average, their yields, and the objects its
first collection examines. We change the workload parameters left open until
the two agree within #117's tolerance, a fifth of the benchmark's yield or half
a point, whichever is wider, and leave the rest as the code and the records set
them. Each one's comment names its source: the code, at the pyperformance
version #117's metadata records, or the record we fitted it to. A placeholder's
comment says neither fixes it yet.

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
  target but one, it would pass a preset that finds no cyclic garbage against a
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
  PEP's pseudocode does not have.
- A start-up for each preset: the five agree within 5% through their first
  collection, and through their second but for connected_components'. Past
  the second the records cannot tell start-up from the benchmark's own work.
- One churn for all of start-up, as this record first had it: each of the
  first two collections examines about 8,000 real objects, where the workers'
  second examines 5,658 to 6,352.
- Start-up's cyclic garbage from the churn: the churn's parameters hold for
  the whole run, and json_loads' loops make no cycles.
- Repeating structures that count their intervals from the run's start, with a
  start-up that fills whole intervals, as create_gc_cycles' does:
  xml_etree_parse's values run 25 MB each, and no start-up fills a whole
  number of them. An offset for each repeating structure would add a workload
  parameter for every request to spell out.
