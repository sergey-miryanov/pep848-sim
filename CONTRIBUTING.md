# Contributing to pep848-sim

pep848-sim is an in-browser explainer for the incremental cycle collector
proposed in [PEP 848](https://peps.python.org/pep-0848/): a Python simulator
of both collectors, run under Pyodide, drawn by a widget embedded in a guide
and a playground. This file is the process. The vocabulary is in
[`CONTEXT.md`](CONTEXT.md) and the decisions are in [`docs/adr/`](docs/adr/).

## Python

The simulator's only real host is Pyodide, so **our Python is Pyodide's
Python**. Today that is 3.14 (Pyodide 314.0.7 runs 3.14.2): develop, type
check and test on 3.14, never on a newer one. When Pyodide moves to a new
Python, move `requires-python`, the ruff, mypy and pyrefly targets, the CI
interpreter and the Pyodide pin together, in one pull request.

## Getting set up

```bash
poetry env use 3.14
poetry install
poetry run pre-commit install
```

The environment lives in `.venv` inside the repo: `poetry.toml` sets
`virtualenvs.in-project`, so editors and tools find it without asking Poetry.
If Poetry cannot find 3.14 by version, give `poetry env use` the full path to
the interpreter. If a `.venv` on another Python is already there, delete it
first: Poetry reuses an in-project `.venv` whatever its version.

## Commands

Every command is a `just` recipe run through Poetry, and CI runs the same
recipes, so a recipe that passes locally passes there. `poetry run just`
lists them.

| Recipe | What it does |
|---|---|
| `check` | `lint`, `typecheck` and `test`: what CI gates on |
| `test` | pytest, Hypothesis invariants included, with the coverage gate |
| `lint` | ruff's checker and formatter |
| `typecheck` | mypy and pyrefly, both strict |
| `site` | assembles `_site/`: copies `site/`, zips `src/pep848_sim` into `_site/sim.zip` |
| `serve` | runs `site`, then serves `_site/` on `http://localhost:8000` |

## Checks

- ruff checks and formats the Python.
- mypy and pyrefly both run in strict mode, and both have to pass.
- pytest runs the example tests and the Hypothesis invariants: no reachable
  object is ever freed, every live object sits in exactly one space, the work
  budget moves by exactly what the counters say, and cyclic garbage wholly in
  the old generation when a sweep starts is freed by its end.
- Coverage below 99% fails the run.
- pre-commit runs ruff, `typos` and `codespell`, `actionlint` and `zizmor`
  over the workflows, and the whitespace hooks. The tree is LF-only.

The JavaScript (the widget and the worker) has no tooling in CI. Every file
starts with `// @ts-check` so an editor type checks it; keep it small.

## The site

There is no build step. `site/` holds hand-written HTML, the widget (one Web
Component, `<gc-widget>`) and the worker. Pyodide and Observable Plot load
from jsDelivr at exact versions. The simulator reaches the browser as
`sim.zip`, which the worker unpacks into Pyodide and imports.

The simulator package never imports from the browser (`js`, `pyodide`): it
is plain Python, which is what lets the tests run it under CPython.

## Publishing

A GitHub Actions workflow runs on every push to `main`: `just check`, then
`just site`, then deploys `_site/` to GitHub Pages at
<https://sergey-miryanov.github.io/pep848-sim/>. A failing check deploys
nothing.

## Where the design lives

- [`CONTEXT.md`](CONTEXT.md) is the glossary, and nothing else. Use its words
  in code, prose and the UI. When a term settles or changes, update it in the
  same pull request.
- [`docs/adr/`](docs/adr/) records decisions and why. If a change overturns
  one, amend the record in the same pull request.

## Opening a pull request

Every change reaches `main` through a pull request, because `main` deploys to
a public page and stays green.

1. Branch off `main`, and run the checks **before changing anything**, so you
   know the tree was green when you started.
```bash
poetry run just check
```
2. Make the change, and keep it to what it names. Problems you spot nearby
   belong in the pull request description, not in the diff.
3. Add tests covering it.
4. Run the checks again.
```bash
poetry run just check
```

Then say what you changed and how you checked it. CI runs the same `check`,
and merging deploys.
