# Make only the transients a collection can see

Transient objects are most of a workload's allocations, and making,
refcounting and freeing them was most of a run's cost in the prototype for
#6. A transient let go at or before the next collection is never examined by
any collection, so the simulator does not make it: drawing its lifetime moves
the allocation clock and nothing else. Only the transients still alive at a
collection become simulated objects. In the prototype, every collection came
out the same as when every transient was made, for both collectors at every
run length, and runs cost 26 to 34% less.

Three things follow. Within each kB, the clock moves, every lifetime that
ends there is let go, and then a collection runs if the kB is a collection
boundary. The heap is read only at collections, as the widget's one record
per collection reads it: between collections, the live count misses the
transients still alive. And the test is a single comparison of a lifetime
with the next boundary only because both collectors collect at the same
boundaries (ADR 0004); if their triggers ever differ, the two runs of a
widget no longer make the same objects.

## Considered Options

- Make every transient: simpler, and about a third slower.
- Count transients per space instead of making them: cheaper still, but no
  longer exact for the collections that do see them.
