# One simulated object stands for 1 kB of real objects

The PEP's defaults (`threshold0` = 2000 kB, about 24 MB of young generation)
mean some 400,000 real objects per young generation, more than pure Python in
the browser can simulate while a reader waits. So each simulated object
stands for 1 kB, about 16 real objects at an assumed 64 B each, and the
collector settings keep the PEP's units and defaults. The simulator divides
by 16 the constants that the PEP or the C implementation count in real
objects: the initial work budget of -100,000 becomes -6,250. The price is
coarse cycles: a three-object cycle in the simulator stands for 3 kB.

The playground lets a reader change the 64 B beside the collector constants
(#154). A simulated object then stands for 1 kB of real objects of the new
size, and the simulator converts each count the PEP gives in real objects by
it, rounding down: at 48 B, the initial work budget of -100,000 real objects
becomes -4,688. The presets keep the numbers ADR 0011 fit at 64 B. Their
lengths come from the records in kB, which the size leaves alone, and we fit
their sizes against those lengths, so scaling the sizes alone would undo the
fit.
