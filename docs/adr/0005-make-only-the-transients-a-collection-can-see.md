# Make only the transients a collection can see

Transient objects are most of a workload's allocations, and making,
refcounting and freeing them was most of a run's cost in the prototype for
#6. No collection examines a transient that the workload lets go of at or
before the next collection, so the simulator does not make it: drawing its
lifetime moves the allocation clock and nothing else. In the prototype, every
collection came out the same as in runs that made every transient, for both
collectors at every run length, and runs cost 26 to 34% less.

Within each kB, the clock moves, the workload lets go of each object whose
lifetime ends there, and then a collection runs if the kB is a collection
boundary. The widget reads the heap once per collection, in that
collection's record: between collections, the live count misses the
transients still alive. Comparing a lifetime with the next boundary is
enough because both collectors collect at the same boundaries (ADR 0004). If
their triggers ever differ, the two runs of a widget no longer make the same
objects.

## Considered Options

- Make every transient: simpler, and about a third slower.
- Count transients per space instead of making them: cheaper still, but no
  longer exact for the collections that do see them.
