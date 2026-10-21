# One simulated object stands for 1 kB of real objects

The PEP's defaults (`threshold0` = 2000 kB, about 24 MB of young generation)
mean roughly 400,000 real objects per young generation, beyond what pure
Python in the browser can simulate interactively. Each simulated object
therefore stands for 1 kB, about 16 real objects at an assumed 64 B each, so
the collector settings keep the PEP's units and defaults. Constants the PEP or
the C implementation count in real objects, such as the initial work budget
of -100,000, are divided by 16 (-6,250). The price is coarse cycles: a
three-object cycle in the simulator stands for 3 kB.
