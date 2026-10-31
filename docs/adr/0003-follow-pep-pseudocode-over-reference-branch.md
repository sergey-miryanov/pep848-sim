# The incremental collector follows the PEP's pseudocode where the reference branch differs

Superseded by ADR 0024: the incremental collector now follows the branch.

The legacy collector is the exception: see ADR 0004.

The reference implementation (`Python/gc.c` on `incremental-gc-update-2`)
settles the work budget once per old collection, after the loop, and loops
`while increment_size < old_work`. The PEP's pseudocode debits and credits the
budget after every increment, so a garbage-rich increment lengthens the
current old collection, where the branch lengthens the next one. The
simulator follows the pseudocode, because the widget explains the PEP as
published. Its work budget curve will differ from `old_work` in gcmon
captures of the branch. Do not "fix" the simulator to match the branch.

## Where the PEP disagrees with itself

The pseudocode starts `young_next` at `False`, so its first collection is an
old one. The PEP's abstract has collections alternate "a young collection,
then an (incremental) old collection", and the reference branch starts there
too: `_PyGC_InitState` never sets `next_gen`, which stays 0, a young
collection. Where the pseudocode contradicts the PEP's own prose and the
branch sides with the prose, the simulator follows the prose, so it starts
with a young collection (#259).
