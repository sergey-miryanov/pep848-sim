# pep848-sim

An interactive explainer for the generational incremental cycle collector
proposed in [PEP 848](https://peps.python.org/pep-0848/). A small Python
simulator of the proposed collector and the legacy one runs in your browser,
and a guide and a playground let you change the workload and the
`gc.set_threshold()` settings and watch what each collector does.

The site, <https://sergey-miryanov.github.io/pep848-sim/>, runs one widget
whose select offers a stand-in workload and five presets modelled on
pyperformance benchmarks: create_gc_cycles, json_loads, xml_etree_parse,
async_tree_io_tg and connected_components. Its playground starts from the
same workloads and lets you change any part of them, in the widget's legend or
as Python, along with the collector constants no Python API changes, and send
what they made by its link. The guide comes next.

- [`CONTRIBUTING.md`](CONTRIBUTING.md): how to set up, run and publish
- [`CONTEXT.md`](CONTEXT.md): the vocabulary
- [`docs/adr/`](docs/adr/): the decisions and why

MIT licensed; see [`LICENSE`](LICENSE).
