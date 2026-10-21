# The legacy collector follows the reference branch's `-X gc=legacy`

The PEP says the legacy collector "will continue to work in the same way as
before", and 3.15 triggers it on the net object count (2000 objects). The
reference branch triggers its `-X gc=legacy` collector on gross kB allocated,
as it does the incremental collector. The simulator models the branch's
legacy collector, so both collectors share one trigger and one `threshold0`
in kB, and a comparison shows the two collection strategies with their
triggers held equal. The simulator takes the branch over the PEP in this one
place (see ADR 0003). Its legacy collector differs from the one CPython 3.15
ships: by default its gen 0 is about 16 times larger.
