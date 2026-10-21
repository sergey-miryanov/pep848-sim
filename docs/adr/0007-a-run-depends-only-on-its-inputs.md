# A run depends only on its inputs

Every reader must see the same charts, so a run is a function of its
workload, seed included, its collector and its collector settings, with
Python and Pyodide pinned. The prototype for #8 found the simulator's records
byte-identical under CPython on Windows and Linux and under Pyodide across
page loads and browsers, in every mode ADRs 0005 and 0006 use. In the same
programs it found what would break that: iterating a set of objects or of
strings and ordering by `id()` or `hash()`, which change with every process
and every page load, and the C library's `log`, `exp`, `sin` and `pow`, which
Windows, Linux and Pyodide each round their own way, up to 1 ulp apart.

Order comes from insertion alone: lists and dicts, sets only for membership,
objects as ints. No C-library floating point, `**` with a float included,
decides anything in a run. Draws are integer-exact (`random()`, `randrange`
and the like), and a lifetime is a `bisect` into exact integer thresholds,
which `fractions` gives for a geometric lifetime, the exponential's
counterpart in whole kB. Each run owns its `random.Random(seed)`, its draws
never depend on what the collector does, and its state lives in its
generator, never at module level. Records hold ints and strings, and the
worker passes them on unchanged. A test pins each preset's records digest
under CPython, and these rules make it Pyodide's digest too. Whoever bumps
Pyodide checks the digests under Pyodide before the bump merges.

## Considered Options

- Keep `expovariate` and trust `int()` to hide the last bit: it did for
  every draw tried, but by luck; about once in 10^17 draws it would not.
- Pin the digests under Pyodide only: every test run would need a browser.
