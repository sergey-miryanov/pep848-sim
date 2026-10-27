# pep848-sim

An interactive explainer for the generational incremental cycle collector
proposed in [PEP 848](https://peps.python.org/pep-0848/). A small Python
simulator of the proposed collector and the legacy one runs in your browser,
and a guide and a playground let you change the workload and the
`gc.set_threshold()` settings and watch what each collector does.

The site, <https://sergey-miryanov.github.io/pep848-sim/>, opens on a widget
whose select offers five presets modelled on pyperformance benchmarks:
xml_etree_parse, create_gc_cycles, json_loads, async_tree_io_tg and
connected_components. Its guide takes PEP 848 a chapter at a time, in steps
beside one widget. Its playground starts from the same workloads and
lets you change any part of them, in the widget's legend or as Python, the
collector constants included, and send what you made by its link.

- [`CONTRIBUTING.md`](CONTRIBUTING.md): how to set up, run and publish
- [`CONTEXT.md`](CONTEXT.md): the vocabulary
- [`docs/adr/`](docs/adr/): the decisions and why

MIT licensed; see [`LICENSE`](LICENSE).
