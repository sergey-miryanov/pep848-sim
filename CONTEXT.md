# PEP 848 GC simulator

An interactive, in-browser explainer for the generational incremental cycle
collector proposed in PEP 848. Readers change workload parameters and
collector settings and watch how the collector behaves next to the legacy one.
Everything below is vocabulary.

## Language

### The thing we build

**Simulator**:
A Python model of both cycle collectors, the incremental one after the PEP's
pseudocode and the legacy one after the reference branch, running over
synthetic objects, never over CPython's own heap.
_Avoid_: emulator, GC (bare), runtime

**Workload**:
A parametrized recipe for what the simulated program does to its heap: what
it allocates, how it links objects, and when it lets go of them.
_Avoid_: benchmark, program, test case

**Preset**:
A named workload with every parameter chosen, modelled by hand on the code of
a pyperformance benchmark. Every preset is one: there are no made-up
workloads. Each carries its own seed and a run length chosen by hand, aiming
at about three sweeps but stopping sooner when sweeps run long.
_Avoid_: benchmark (that is the real program it is modelled on), scenario,
example, template

**Workload parameter**:
One knob that shapes a workload: the churn's fate mix and cycle size, a
structure's shape, size, root, lifetime and rebuild interval, and the churn
per built object.
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
25% long-lived ratio of the legacy collector. Unlocked in the playground only.
_Avoid_: setting (that is what Python can change), magic number, tunable

### Scale and time

**Simulated object**:
The unit the simulator allocates, links and collects. Each stands for 1 kB of
real objects, so the collector settings keep the PEP's units and defaults.
_Avoid_: chunk, block, cell, node (that is how one is drawn)

**Real object**:
A CPython object, assumed to be 64 B on average, so one simulated object
stands for 16 of them. Counts the PEP or the C implementation give in real
objects shrink by the same 16 inside the simulator. The 64 B is an assumption,
not a collector constant, and the playground lets a reader change it.
_Avoid_: object (bare, when the two could be confused), PyObject

**Allocation clock**:
The simulator's only notion of time: kB allocated since the run began.
Lifetimes, collection triggers and every chart's x-axis read it.
_Avoid_: time (bare), wall time, steps, ticks

### What happens to an object

**Background churn**:
The objects a workload allocates outside any structure, each drawing its own
fate: transient, or one of a small cycle that becomes cyclic garbage.
_Avoid_: noise, filler, temporaries

**Fate**:
What becomes of an object: transient, cyclic garbage, or long-lived. Churn
draws one per object at allocation; a structure's objects share the one its
shape and lifetime imply. Never changes.
_Avoid_: type, kind, class (all three are Python's words for something else)

**Transient object**:
An object refcounting frees once its lifetime ends. Never garbage the
collector has to find.
_Avoid_: short-lived (cyclic garbage can be short-lived too), temporary

**Cyclic garbage**:
Objects in a cycle that the workload has let go of. Only the collector can
free them.
_Avoid_: leak, garbage (bare), dead objects

**Long-lived object**:
An object in a long-lived structure, reachable until the run ends.
_Avoid_: immortal (CPython's immortal objects are a different thing),
permanent, static

**Structure**:
Objects a workload builds in one shape, hangs off one root, and drops together
when its lifetime ends. A repeating structure is rebuilt at a fixed interval,
the way a benchmark rebuilds its data each iteration. Dropped, a structure
whose shape has cycles becomes cyclic garbage; one without is freed by
refcounting on the spot.
_Avoid_: data structure (fine in prose), object graph (that is the whole
heap), cluster

**Build**:
The stretch of the allocation clock in which one structure is allocated. Each
built object is followed by a fixed number of churn allocations, the build's
churn, so a build is spread over more kB than the structure holds. Builds of
a repeating structure never overlap.
_Avoid_: construction, setup, phase, iteration (that is the benchmark's word
for a build plus everything until the next one)

**Long-lived structure**:
A structure that is never dropped.
_Avoid_: live set (that includes transient objects still in use), data,
cache

**Shape**:
A named pattern a structure is built in, such as a list of records
or a tree: which references its objects hold, and the order a Python program
would allocate them in.
_Avoid_: topology, layout, kind, type

**Root**:
Something outside the heap that keeps objects reachable. Either a module root
or a frame root.
_Avoid_: anchor, owner, GC root (bare; the two kinds behave differently)

**Module root**:
`sys`, and through it every module global. Old collections mark what it
reaches, so objects hung off it never join an increment.
_Avoid_: global root, static root

**Frame root**:
A reference held by a running frame, such as a local in `main()`. Marking
never starts from one, so objects hung only off a frame root reach the
collector through increments.
_Avoid_: stack root, local root, C root

**Lifetime**:
How long, on the allocation clock, an object or a structure stays reachable
after it is allocated. Long-lived structures outlast the run.
_Avoid_: age (that is how long it has existed, reachable or not), TTL

### What readers see

**Widget**:
One embedding of the simulator on a page: a preset, the controls a reader is
allowed to change, and the charts of the runs it makes.
_Avoid_: demo, applet, visualization, simulator (that is what it runs)

**Guide**:
The long-form page that explains PEP 848 section by section, each section
embedding a widget with its preset and one or two controls.
_Avoid_: tutorial, article, docs

**Playground**:
The page with one widget and every control unlocked, for readers who want to
try anything.
_Avoid_: sandbox, lab, explorer

**Run**:
One simulation of one workload by one collector under one set of collector
settings, from an empty heap to the preset's run length on the allocation
clock. A widget comparing the collectors makes two runs of the same workload,
which allocate the same objects in the same order.
_Avoid_: simulation (bare), trial, execution, benchmark

**Uncollected garbage**:
Objects already unreachable that no collection has freed yet: the gap
between the heap and its reachable part. Only a simulator can draw it, since
a real collector learns what is garbage only by collecting it.
_Avoid_: floating garbage (the literature's word for garbage that dies during
a collection), leak, dead objects

**Peak work**:
The largest work any single collection did in a run: the simulator's
stand-in for the worst pause.
_Avoid_: worst pause, max pause, `max_pause` (the C stat, in seconds)

**Work per MB**:
A run's total work over the MB it allocated: the simulator's stand-in for GC
overhead.
_Avoid_: overhead, GC share, CPU percentage

### Collectors

**Incremental collector**:
The collector PEP 848 proposes: alternates young collections with increments
of the old generation.
_Avoid_: new GC, incgc, inc GC

**Legacy collector**:
The three-generation collector as the reference branch keeps it behind
`-X gc=legacy`: triggered by gross kB allocated, like the incremental
collector, rather than by the net object count 3.15 uses.
_Avoid_: old GC (collides with the old generation), classic, generational GC
(both collectors are generational), current GC, 3.15 GC (3.15's triggers
differently)

**Gen 0, gen 1, gen 2 collection**:
The legacy collector's three collections, named for the oldest generation
each takes: the nursery; the nursery and aging; the whole heap. Used for the
legacy collector only.
_Avoid_: young, minor, major (and any genN word for the incremental
collector)

### The heap

**Nursery**:
The generation newly allocated objects enter. A single space.
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
Where objects that survive the young generation live. Split into a pending
space and a visited space by the incremental collector.
_Avoid_: gen2, tenured

**Pending space**:
The part of the old generation the current sweep has not yet marked or
examined.
_Avoid_: unscanned, to-do

**Visited space**:
The part of the old generation the current sweep has already marked or
examined, plus whatever young collections promoted during it. Pending and
visited swap roles when pending runs empty.
_Avoid_: scanned, done

### Collections

**Young collection**:
A collection of the oldest aging space, whose survivors move to the visited
space.
_Avoid_: gen0 collection, minor GC (in the incremental collector `gc.collect(0)`
is a young collection, not a collection of generation 0)

**Increment**:
The transitive closure of pending objects reachable from the least recently
scanned pending object, collected as one unit. Always contains whole cycles.
_Avoid_: chunk, slice, batch, step

**Old collection**:
One turn of the incremental collector on the old generation: zero or more
increments, collected while the work budget stays positive.
_Avoid_: gen1, generation 1 (the stats slot the C implementation files it
under, which reads as the aging generation), major GC, full collection (that
is `gc.collect()`, the whole heap)

**Sweep**:
One pass of the incremental collector over the whole old generation, from one
swap of pending and visited to the next, in which every object that was old
at the swap is marked or examined once. Only the work budget moves it along,
so it runs long when few objects survive and short when garbage is plentiful.
Cyclic garbage wholly in the old generation when a sweep starts is freed by
the time it ends. The legacy collector has none; a gen 2 collection does the
same ground in one go.
_Avoid_: cycle, GC cycle (both collide with reference cycles), pass, epoch,
full collection (that is `gc.collect()`)

### What a collection did

**Work**:
What a collection cost: every simulated object it marked or examined, so
marked + survived + freed. The simulator's stand-in for pause time.
_Avoid_: pause, duration, time, cost (all promise a clock the simulator does
not have)

**Marked**:
Objects an old collection moved from pending to visited because they are
reachable, without examining them for cycles.
_Avoid_: scanned (every kind of work scans), visited (that is the space)

**Survived**:
Objects a collection examined for cycles and moved on, to the visited space.
_Avoid_: promoted, kept, live

**Freed**:
Objects a collection examined and found to be cyclic garbage.
_Avoid_: collected (reads as the act, not the count), reclaimed, swept

**Yield**:
Freed over freed + survived: the share of the objects a collection examined
that turned out to be garbage. Marked objects are left out, since they were
never examined. Independent of scale, so a preset's yield can be held against
`collected / candidates` from a real run of its benchmark.
_Avoid_: efficiency, hit rate, garbage ratio

**Idle collection**:
A collection that triggered and did no work: marked, survived and freed are
all zero. An old collection is idle whenever the work budget is not positive;
a young collection is idle when the aging space it takes is empty, as the
first few are at startup.
_Avoid_: skipped, empty, no-op, wasted (a collection that only marks is not
wasted)

### The work budget

**Work budget**:
How much old-generation scanning the incremental collector owes, as the PEP's
pseudocode keeps it. Young collections credit it with their survivors; each
increment debits it with what it examined and credits it with twice what it
freed, straight away, so a garbage-rich increment lengthens the old collection
it is part of. Spelled `work_to_do` when quoting the PEP.
_Avoid_: old_work (the C implementation's counterpart, which is settled once
per old collection and so traces a different curve), debt, credit
