# The incremental collector follows the PEP's pseudocode where the reference branch differs

The legacy collector is the exception: see ADR 0004.

The reference implementation (`Python/gc.c` on `incremental-gc-update-2`)
settles the work budget once per old collection, after the loop, and loops
`while increment_size < old_work`. The PEP's pseudocode debits and credits the
budget after every increment, so a garbage-rich increment lengthens the
current old collection, where the branch lengthens the next one. The
simulator follows the pseudocode, because the widget explains the PEP as
published. Its work budget curve will differ from `old_work` in gcmon
captures of the branch. Do not "fix" the simulator to match the branch.
