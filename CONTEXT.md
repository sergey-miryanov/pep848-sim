# PEP 848 GC simulator

An interactive, in-browser explainer for the generational incremental cycle
collector that PEP 848 proposes. Readers change workload parameters and
collector settings and watch the collector work beside the legacy one.
Everything below is vocabulary.

## Language

### The thing we build

**Simulator**:
A Python model of both cycle collectors, the incremental one after the PEP's
pseudocode and the legacy one after the reference branch, running over
synthetic objects.
_Avoid_: emulator, GC (bare), runtime

**Workload**:
A parametrized recipe for what the simulated program does to its heap: what
it allocates, how it links objects, and when it lets go of them.
_Avoid_: benchmark, program, test case

**Preset**:
A named workload with every workload parameter chosen by hand to model one
worker of a pyperformance benchmark, from interpreter start-up to shutdown.
Every preset has a benchmark behind it: there are no made-up workloads. Each
carries its own seed, and runs for its worker's own length on the allocation
clock, shutdown included.
_Avoid_: benchmark (that is the real program it is modelled on), scenario,
example, template

**Worker**:
One process pyperf starts to run a benchmark: interpreter start-up, imports,
the benchmark's loops, and shutdown with its full collections. gcmon records
each worker's collections, and a preset models one worker.
_Avoid_: process (bare), run (that is the simulator's), job

**Shutdown**:
The end of a worker. Its frames have returned, `_Py_Finalize` runs a full
collection, and `finalize_modules` lets go of the modules and runs two more. A
run ends in shutdown when its workload asks for one.
_Avoid_: exit, teardown, finalization (bare)

**Workload parameter**:
One knob that shapes a workload: the churn's fate mix, cycle size and
lifetimes; a structure's shape, size, root, lifetime, rebuild interval and
full collections, and whether a frame holds it while it builds before sys takes
it; the churn per built object; and whether the run ends in shutdown.
_Avoid_: parameter (bare), setting (that is the collector's side), option

**Collector setting**:
One knob of the collector itself that Python lets a program turn: which
collector runs, and the three thresholds of one `gc.set_threshold()` call,
which both collectors in a widget share and each reads its own way.
_Avoid_: parameter (bare), threshold (bare, unless naming one of the three),
config

**Collector constant**:
A number fixed inside a collector that no Python API changes: the initial
work budget and the freed-credit multiplier of the incremental collector, the
25% long-lived ratio of the legacy collector. The home page's widget and the
playground unlock them.
_Avoid_: setting (that is what Python can change), magic number, tunable

### Scale and time

**Simulated object**:
The unit the simulator allocates, links and collects. Each stands for 1 kB of
real objects, so the collector settings keep the PEP's units and defaults.
_Avoid_: chunk, block, cell, node (that is how one is drawn)

**Real object**:
A CPython object of a type the cycle collector supports, such as a list, a
dict, a tuple or an instance. The simulator assumes 64 B for one on average,
so one simulated object stands for 16 of them. Strings, numbers and the other
objects the collector never sees fall outside the term: they enter no space
and leave the allocation clock where it is. The simulator divides by the same
16 any count the PEP or the C implementation gives in real objects. The 64 B
is an assumption, outside the collector constants, and the playground lets a
reader change it beside them.
_Avoid_: object (bare, when the two could be confused), PyObject, tracked
object (a real object can be untracked after it is allocated, as a
collection does to a tuple that holds only numbers)

**Allocation clock**:
The simulator's only notion of time: kB of real objects allocated since the
run began, counted as the collectors' trigger counts them, at allocation.
Lifetimes, collection triggers and every chart's x-axis read it.
_Avoid_: time (bare), wall time, steps, ticks

### What happens to an object

**Background churn**:
The objects a workload allocates outside any structure, each drawing its own
fate: transient, or one of a small cycle that becomes cyclic garbage.
_Avoid_: noise, filler, temporaries

**Fate**:
An object's outcome: transient, cyclic garbage, or long-lived. Churn draws
one per object at allocation; a structure's objects share the one its shape
and lifetime imply. An object keeps its fate from allocation on.
_Avoid_: type, kind, class (all three are Python's words for something else)

**Transient object**:
An object that refcounting frees once its lifetime ends, leaving the
collector nothing to find.
_Avoid_: short-lived (cyclic garbage can be short-lived too), temporary

**Cyclic garbage**:
Objects in a cycle that the workload has let go of. The collector alone can
free them.
_Avoid_: leak, garbage (bare), dead objects

**Long-lived object**:
An object in a long-lived structure, reachable until the run ends.
_Avoid_: immortal (CPython's immortal objects are a different thing),
permanent, static

**Object graph**:
The heap's objects and the references between them. The widget draws a
sample of it: a few objects of each structure.
_Avoid_: heap graph, reference graph

**Structure**:
Objects a workload builds in one shape, hangs off one root, and drops together
when its lifetime ends. The workload rebuilds a repeating structure at a
fixed interval, the way a benchmark rebuilds its data each iteration.
Dropped, a structure whose shape has cycles becomes cyclic garbage, and
refcounting frees one without on the spot.
_Avoid_: data structure (fine in prose), object graph (that is the whole
heap), cluster

**Build**:
The stretch of the allocation clock in which the workload allocates one
structure. The workload follows each built object with a fixed number of
churn allocations, the build's churn, so a build spreads over more kB than
the structure holds. Builds of a repeating structure never overlap.
_Avoid_: construction, setup, phase, iteration (that is the benchmark's word
for a build plus everything until the next one)

**Long-lived structure**:
A structure the workload never drops.
_Avoid_: live set (that includes transient objects still in use), data,
cache

**Shape**:
A named pattern the workload builds a structure in, such as a list of records
or a tree: which references its objects hold, and the order a Python program
would allocate them in.
_Avoid_: topology, layout, kind, type

**Own shape**:
A shape a reader writes on the playground: Python that gives the links each
new object brings.
_Avoid_: custom shape, user shape, plugin

**Root**:
Something outside the heap that keeps objects reachable: a module root or a
frame root.
_Avoid_: anchor, owner, GC root (bare; the two kinds behave differently)

**Module root**:
`sys`, and through it every module global. Old collections mark what it
reaches, so objects hung off it never join an increment.
_Avoid_: global root, static root

**Frame root**:
A reference a running frame holds, such as a local in `main()`. Old
collections never mark from one, so objects hung off frame roots alone reach
the collector through increments.
_Avoid_: stack root, local root, C root

**Lifetime**:
The span of the allocation clock that an object or a structure stays
reachable after its allocation. Long-lived structures outlast the run.
_Avoid_: age (that is how long it has existed, reachable or not), TTL

**Churn lifetime**:
The lifetime that background churn draws for each transient and each cycle:
geometric in whole kB, with a mean the workload sets. Transients in the long
share draw theirs from a range of kB past the young generation instead, each
kB in it as likely as the next, so that some reach the old generation.
_Avoid_: lifespan, half-life (a geometric lifetime has one, but the word
promises decay)

**Alive**:
An object the heap has allocated and not yet freed, reachable or not. The
heap tells alive from freed; a collector tells reachable, unreachable and
freed apart. Its allocating frame holds a new object, as in CPython, until the
workload lets go of that frame root.
_Avoid_: existing, allocated (that is the act of making it)

### What readers see

**Widget**:
One embedding of the simulator on a page: one preset or a choice of several,
the controls a reader may change for each, and the charts of the runs it makes.
_Avoid_: demo, applet, visualization, simulator (that is what it runs)

**Control**:
A slider the page puts on a widget for one workload parameter, collector
setting or collector constant. The widget groups them: the workload's, then the
collector's. Moving one changes only the value it shows; releasing it starts
the widget's two runs again, or draws the ones it kept for the same values.
Its range keeps the workload valid.
_Avoid_: knob (that is the parameter, setting or constant it moves), input,
option

**Guide**:
The long-form page that explains PEP 848 section by section, each section
embedding a widget with its preset and one or two controls.
_Avoid_: tutorial, article, docs

**Playground**:
The page with one widget whose legend edits the whole workload, the run
length, the collector settings and the collector constants, for readers who
want to try anything. Each change starts the widget's two runs again, as a
control's release does. A switch shows the workload source in place of the
legend's editor.
_Avoid_: sandbox, lab, explorer

**Playground link**:
The playground's address once a run has started: it holds the workload, the
run length, the collector settings and the collector constants, and opens the
same runs in another browser. A link with a shape of the reader's own opens its
workload source and waits for the reader to run it.
_Avoid_: permalink, share URL, deep link, link (bare, when another could be
meant)

**Workload source**:
The playground's other editor: the workload, the run length, the collector
settings and the collector constants as Python beside the widget. The reader
runs it with a button, and the legend then shows the workload it made.
_Avoid_: script, program, code view, source (bare, where the site's own source
code could be meant)

**Run**:
One simulation of one workload by one collector under one set of collector
settings, from an empty heap to the preset's run length on the allocation
clock, and on through shutdown if the workload asks for one. A widget
comparing the collectors makes two runs of the same workload, which allocate
the same objects in the same order.
_Avoid_: simulation (bare), trial, execution, benchmark

**Uncollected garbage**:
Unreachable objects that no collection has freed: the gap between the heap
and its reachable part. A simulator can draw it. A real collector learns
which objects are cyclic garbage as it collects them, too late to draw the
gap.
_Avoid_: floating garbage (the literature's word for garbage that dies during
a collection), leak, dead objects

**Peak work**:
The largest work any single collection the runtime started did in a run: the
simulator's stand-in for the worst pause. A full collection takes the whole
heap in either collector by design, so peak work leaves it out.
_Avoid_: worst pause, max pause, `max_pause` (the C stat, in seconds)

**Work per MB**:
A run's total work over the MB it allocated: the simulator's stand-in for GC
overhead.
_Avoid_: overhead, GC share, CPU percentage

### Collectors

**Incremental collector**:
The collector PEP 848 proposes. It alternates young collections with
increments of the old generation.
_Avoid_: new GC, incgc, inc GC

**Legacy collector**:
The three-generation collector as the reference branch keeps it behind
`-X gc=legacy`. Gross kB allocated trigger it, as they trigger the
incremental collector; 3.15 triggers it on the net object count.
_Avoid_: old GC (collides with the old generation), classic, generational GC
(both collectors are generational), current GC, 3.15 GC (3.15's triggers
differently)

**Gen 0, gen 1, gen 2 collection**:
The legacy collector's three collections, named for the oldest generation
each takes: the nursery; the nursery and aging; the whole heap. The terms
belong to the legacy collector alone.
_Avoid_: young, minor, major (and any genN word for the incremental
collector)

### The heap

**Nursery**:
The generation new objects enter: a single space.
_Avoid_: gen0, young space, eden

**Half-space**:
`threshold0` kB, the unit the PEP sizes the young generation in. The nursery
is two half-spaces, and `threshold1` counts the aging generation's.
_Avoid_: half space (two words), segment, unit (bare)

**Aging generation**:
The generation between the nursery and the old generation: `threshold1 / 2`
aging spaces, rounded up.
_Avoid_: gen1, middle generation, young generation (that is nursery and aging
together)

**Aging space**:
One former nursery, two half-spaces, waiting in the aging generation until it
is the oldest and a young collection takes it.
_Avoid_: half-space (that is half of one), bucket, slot

**Old generation**:
The generation objects reach once they survive the young generation. The
incremental collector splits it into a pending space and a visited space.
_Avoid_: gen2, tenured

**Pending space**:
The part of the old generation the current sweep has left to mark or
examine.
_Avoid_: unscanned, to-do

**Visited space**:
The part of the old generation the current sweep has marked or examined,
plus the survivors of the young collections during it. Pending and visited
swap roles when pending runs empty.
_Avoid_: scanned, done

### Collections

**Young collection**:
A collection of the oldest aging space, whose survivors move to the visited
space.
_Avoid_: gen0 collection, minor GC (in the incremental collector `gc.collect(0)`
is a young collection, not a collection of generation 0)

**Increment**:
The transitive closure of pending objects reachable from the least recently
scanned pending object, which an old collection collects as one unit. It
contains each cycle it touches in full.
_Avoid_: chunk, slice, batch, step

**Old collection**:
One turn of the incremental collector on the old generation: zero or more
increments, which it collects while the work budget stays positive.
_Avoid_: gen1, generation 1 (the stats slot the C implementation files it
under, which reads as the aging generation), major GC, full collection (that
takes the whole heap)

**Sweep**:
One pass of the incremental collector over the whole old generation, from one
swap of pending and visited to the next, in which the collector marks or
examines once each object that was old at the swap. The work budget alone
paces it, so it runs long when few objects survive and short when cyclic
garbage is plentiful. Cyclic garbage wholly in the old generation when a
sweep starts is freed by the time it ends, unless newer garbage holds it,
which leaves it for a later sweep. The legacy collector has no sweeps; a gen
2 collection covers the same ground in one go.
_Avoid_: cycle, GC cycle (both collide with reference cycles), pass, epoch,
full collection (that takes the whole heap in one go)

**Full collection**:
A collection of the whole heap in one go, which a workload asks for with
`gc.collect()` and shutdown runs three times. The legacy collector runs a gen 2
collection; the incremental collector marks what the module root reaches and
examines everything else, whatever space it sits in.
_Avoid_: major GC, whole-heap collection, gen 2 collection (that names the
legacy collector's automatic one), sweep

### What a collection did

**Work**:
The count of simulated objects a collection marked or examined: marked +
survived + freed. The simulator's stand-in for pause time.
_Avoid_: pause, duration, time, cost (all promise a clock the simulator does
not have)

**Marked**:
Objects an old collection moved from pending to visited because they are
reachable, without examining them for cycles.
_Avoid_: scanned (every kind of work scans), visited (that is the space)

**Survived**:
Objects a collection examined for cycles and moved on: to the visited space
in the incremental collector, to an older generation in the legacy one.
_Avoid_: promoted, kept, live

**Freed**:
Objects a collection examined and freed: the cyclic garbage it found, and any
object it kept that refcounting freed when it cleared that garbage.
_Avoid_: collected (reads as the act, not the count), reclaimed, swept

**Yield**:
Freed over freed + survived: the share of the objects a collection examined
that were cyclic garbage. It leaves marked objects out, since the collection
never examined them. Scale drops out of it, so you can hold a preset's yield
against `collected / candidates` from a real run of its benchmark.
_Avoid_: efficiency, hit rate, garbage ratio

**Record**:
What one collection did, with the heap before it and after it: by space, and
as its reachable part. A run yields its records as it goes, and the widget's
charts draw them.
_Avoid_: stats (CPython's counters per generation), sample, snapshot (a
record reads the heap twice), event

**Idle collection**:
A collection that triggered and did no work: marked, survived and freed are
all zero. An old collection is idle whenever the work budget is not positive;
a young collection is idle when the aging space it takes is empty, as the
first few are at startup.
_Avoid_: skipped, empty, no-op, wasted (a collection that only marks is not
wasted)

### The work budget

**Work budget**:
The old-generation scanning the incremental collector owes, as the PEP's
pseudocode keeps it. Young collections credit it with their survivors, and
old collections debit it with what they mark. Each increment debits it with
what it examined and credits it with twice what it freed, straight away, so
a garbage-rich increment lengthens the old collection it is part of. Quoting
the PEP, spell it `work_to_do`.
_Avoid_: old_work (the C implementation's counterpart, which is settled once
per old collection and so traces a different curve), debt, credit
