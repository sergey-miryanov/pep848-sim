# A full collection follows the reference branch

PEP 848 says `gc.collect()`, with no argument or with 2, collects the whole
heap, and gives no pseudocode for it. The incremental collector follows the
PEP's pseudocode (ADR 0003), so where the pseudocode stops, the simulator
follows the reference branch's `gc_collect_incremental_full` in
`Python/gc.c`. Every object joins the pending space. The collector moves what
`sys` reaches to the visited space without examining it, as an old collection
marks, then examines the rest and moves the survivors to visited too. The work
budget starts again from 0, and with pending empty, the next old collection
that has a positive budget swaps the spaces and starts a new sweep. Young and
old collections keep alternating as before. The legacy collector runs a gen 2
collection, as the branch does for `gc.collect()` under `-X gc=legacy`.

Every collection on the branch resets the allocation budget (ADR 0011), a
full one included, so the next automatic collection comes `threshold0` kB
after it. A workload that never calls `gc.collect()` collects where it did
before.

Two things call a full collection. A structure can ask for one before each
build and one after each drop, as create_gc_cycles calls `gc.collect()`
around each loop. A run can end in shutdown, as a worker does. By the time
`finalize_modules` runs, the worker's frames have returned, so the heap lets
go of every frame root and two full collections follow. The record names the
kind: `full` for `gc.collect()` and `shutdown` for the last two, in both
collectors. `gen 2` stays the legacy collector's automatic collection, so a
preset's records split into automatic and explicit collections the way #117
splits its benchmark's. The figures count a full collection like any other,
and leave it out of the gen 2 count.

## Considered Options

- Run old collections until a sweep ends. That uses only the PEP's own
  pieces, but the budget sets a sweep's length, and the branch's
  `gc.collect()` takes the whole heap in one go.
- Record a legacy full collection as `gen 2`, as the branch's stats file it.
  That hides which gen 2 collections the runtime started.
- Let shutdown's collections find the heap as the run left it. Whatever the
  frames held would survive them, and churn would need the run length in
  advance to make the transients alive at the end (ADR 0005).
- Call `gc.collect()` every so many kB. Churn would know each call in
  advance, but a preset would have to keep the calls in step with its
  structure by hand, and a build that waits would shift them.
