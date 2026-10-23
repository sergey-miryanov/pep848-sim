# pep848-sim

An interactive explainer for the generational incremental cycle collector
proposed in [PEP 848](https://peps.python.org/pep-0848/). A small Python
simulator of the proposed collector and the legacy one runs in your browser,
and a guide and a playground let you change the workload and the
`gc.set_threshold()` settings and watch what each collector does.

The site, <https://sergey-miryanov.github.io/pep848-sim/>, runs the widget on a
stand-in workload today, and on the first preset, create_gc_cycles, beside
it. More presets modelled on pyperformance benchmarks come next, then the
guide.

- [`CONTRIBUTING.md`](CONTRIBUTING.md): how to set up, run and publish
- [`CONTEXT.md`](CONTEXT.md): the vocabulary
- [`docs/adr/`](docs/adr/): the decisions and why

MIT licensed; see [`LICENSE`](LICENSE).
