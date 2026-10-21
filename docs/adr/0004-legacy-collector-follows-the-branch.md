# The legacy collector follows the reference branch, not 3.15

The PEP says the legacy collector "will continue to work in the same way as
before", and 3.15 triggers it on net tracked allocations (2000 objects). The
reference branch instead triggers its `-X gc=legacy` collector on gross kB
allocated, the same as the incremental collector. The simulator models the
branch's legacy collector, so both collectors share one trigger and one
`threshold0` in kB, and a comparison shows the difference between the two
collection strategies rather than a difference in when they fire. This is
the one place the simulator takes the branch over the PEP (see ADR 0003), and
its legacy collector is not the one CPython 3.15 ships: its gen 0 is about 16
times larger by default.
