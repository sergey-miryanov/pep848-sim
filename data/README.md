# Benchmark data

The presets' yield targets come from these files. Each collector has a table,
a row per collection, with its metadata beside it. `tools/benchmarks.py` loads
them for the tests, and `sim.zip` never ships them.

**The files here are mock.** `tools/mock_data.py` wrote them in the layout
#117 sets out, so the loader and the tests that read it could land before the
rerun. The script made up every number in them, and each metadata file says
`"mock": true`, so don't fit a preset to them.

The rerun of pyperformance under gcmon on the reference branch, once with the
incremental collector and once with `-X gc=legacy`, replaces them (#117).
`tools/mock_data.py` goes in the same change.
