# Benchmark data

The presets' yield targets come from these files. gcmon traced pyperformance
1.14.0 on the reference branch, at revision 5542f2021c2, once under each
collector, and extracted each trace into a CSV file, a row per collection,
with its metadata beside it.

| Files | Collector |
|---|---|
| `pp-inc.csv`, `pp-inc.meta.json` | incremental |
| `pp-legacy.csv`, `pp-legacy.meta.json` | legacy, under `-X gc=legacy` |

Each metadata file names its trace and the trace's SHA-256, the Python build,
pyperformance's and pyperf's versions and the date. The traces stay out of the
repo. The collector and the thresholds are columns: `gc_type`, 2 for the
incremental collector and 1 for the legacy one, and `threshold0` to
`threshold2`, the PEP's 2000, 10 and 10.

`tools/benchmarks.py` loads the CSV files for the tests, and `sim.zip` never
ships them. It leaves out pyperf's calibration workers, the processes with no
benchmark's name, and shutdown's collections: gcmon reads a worker once a tick,
and a worker can exit before gcmon reads them. `poetry run just compare`
prints each preset's collections beside its benchmark's, for fitting a preset
by hand (ADR 0011), and the yield test holds them together. `poetry run just
plot` draws them a collection at a time over each of the benchmark's workers,
on a page that runs no Pyodide and ships nowhere. Besides the five
benchmarks the presets model, the files hold shortest_path and three more
xml_etree benchmarks.

A fresh trace replaces both pairs of files whole, under the same names, and
moves every target with it.
