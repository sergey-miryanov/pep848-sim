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
interpreter (in `.github/actions/setup`, which both workflows use) and the
Pyodide pin, in `site/worker.js` and `package.json`, together, in one pull
request.

## Getting set up

```bash
poetry env use 3.14
poetry install
poetry run pre-commit install
npm ci
```

The environment lives in `.venv` inside the repo: `poetry.toml` sets
`virtualenvs.in-project`, so editors and tools find it without asking Poetry.
If Poetry cannot find 3.14 by version, give `poetry env use` the full path to
the interpreter. If a `.venv` on another Python is already there, delete it
first: Poetry reuses an in-project `.venv` whatever its version.

`npm ci` installs tsc and Pyodide into `node_modules`, at the versions
`package-lock.json` locks. It needs Node 24, the version CI runs. Node's own
test runner runs the widget's tests and the Pyodide check, so neither takes a
test framework.

## Commands

Every command is a `just` recipe run through Poetry, and CI runs the same
recipes, so a recipe that passes locally passes there. `poetry run just`
lists them.

| Recipe | What it does |
|---|---|
| `check` | `check-py`, `check-ts`, `test-js` and `test-pyodide`: what CI gates on |
| `check-py` | `lint`, `typecheck` and `test`: the Python |
| `check-ts` | tsc over the site's JavaScript and its tests |
| `test-js` | Node's test runner over the widget's JavaScript |
| `test-pyodide` | the pinned runs' digests under Pyodide, in Node: about 13 s |
| `test` | pytest, Hypothesis invariants included, with the coverage gate |
| `lint` | ruff's checker and formatter |
| `typecheck` | mypy and pyrefly, both strict |
| `site` | assembles `_site/`: the pages at the top, and the rest of `site/` with `src/pep848_sim` zipped as `sim.zip` in `v/<commit>/`; `--keep REF` keeps the folder the site at `REF` serves too |
| `serve` | runs `site`, then serves `_site/` on `http://localhost:8000` |
| `compare` | runs each preset under both collectors and prints its collections beside its benchmark's in `data/` |

`test` passes its arguments to pytest. To run one test file, leave the
coverage gate out: `poetry run just test tests/test_smoke.py --no-cov`.

## Checks

- ruff checks and formats the Python.
- mypy and pyrefly both run in strict mode, and both have to pass. A pyrefly
  warning fails the check as an error does.
- tsc checks the site's JavaScript from its JSDoc, in strict mode: the page's
  scripts and the tests against the DOM (`tsconfig.json`), and the worker
  against a web worker's globals (`tsconfig.worker.json`).
- Node's test runner runs `tests/*.test.js` against `site/panels.js`, which
  turns a run's records into what each panel draws. `panels.js` imports neither
  Plot nor the DOM, so Node can load it. The tests stay out of `site/`, which
  `just site` publishes whole.
- Node runs `tests/digests.pyodide.js` under Pyodide, from npm at the version
  the site's worker loads. It sends each request `tests/digests.json` pins
  through `pep848_sim.widget.request`, the worker's path, and each run's
  records must give the digest pytest pins under CPython (ADR 0007).
- pytest runs the example tests and the Hypothesis invariants: no reachable
  object is ever freed, every alive object sits in exactly one space, the work
  budget moves by exactly what the counters say, and cyclic garbage wholly in
  the old generation when a sweep starts is freed by its end, unless newer
  garbage holds it.
- Coverage below 99% fails the run. CI uploads the report to Codecov, which
  holds the project to the same 99% and the lines a pull request changes to
  90%.
- pre-commit runs ruff, `typos` and `codespell`; `check-jsonschema`,
  `actionlint` and `zizmor` over the workflows; the whitespace hooks; and
  checks for broken YAML, TOML and XML, merge conflict markers, symlinks, and
  file names Windows cannot check out. The tree is LF-only. pre-commit.ci
  runs the same hooks on every pull request.
- Hook revisions are pinned by commit SHA, the tag in a `# frozen:` comment.
  Dependabot moves them, the Python and npm packages and the actions daily,
  once a release is a week old. pre-commit.ci's own update runs only
  quarterly, and it and `poetry run pre-commit autoupdate --freeze` both pin
  an annotated tag's own SHA rather than its commit: take the commit from
  `git ls-remote <repo> 'refs/tags/<tag>^{}'`. Keep ruff's at the version in
  `poetry.lock`.

Every JavaScript file starts with `// @ts-check`, so an editor checks it as
`check-ts` does. tsc emits nothing, and the browser runs the files as written;
keep them small.

## The package

`src/pep848_sim` has three parts. A module imports from its own part and the
parts listed before it, never from one after:

1. `pep848_sim.collectors`: the heap and the two collectors, which ADRs 0003
   and 0004 govern.
2. `pep848_sim` itself: the workload, its structures and a run.
3. `pep848_sim.widget`: what the page's worker calls, the request and the
   figures.

`tests/test_parts.py` reads every module's imports and fails on one against
that order. It also fails on a new package until its `PARTS` names it, so
whoever adds one decides where it stands. The tests stay in one folder, since
they import strategies and helpers from one another.

## The site

There is no build step. `site/` holds hand-written HTML, the widget (one Web
Component, `<gc-widget>`) and the worker. `theme.css` holds the colors of
every page and the widget, and `theme.js` picks the light or the dark theme
(ADR 0018). Pyodide, Observable Plot and
d3-force load from jsDelivr at exact versions. The simulator reaches the browser as
`sim.zip`, which the worker unpacks into Pyodide and imports. `just site`
copies the pages to the top of `_site/` and every other file into a folder
named for the commit, which the pages' links name, so each page loads the
files it was deployed with (ADR 0019).

The simulator package never imports from the browser (`js`, `pyodide`): it
is plain Python, which is what lets the tests run it under CPython.

## Publishing

A GitHub Actions workflow runs on every push to `main`: `just check`, then
`just site --keep` on the live `gh-pages` branch, which keeps the folder the
live site serves beside the new one, then pushes `_site/` to `gh-pages`, which
GitHub Pages serves at <https://sergey-miryanov.github.io/pep848-sim/>. A failing
check deploys nothing. `site/.nojekyll` stops Pages running Jekyll over the
files.

Each pull request gets a preview. Another workflow builds the pull request's
site and pushes it to `pr-preview/pr-N/` on the same branch, and a comment on
the pull request links it. Closing the pull request removes the preview, and
a deploy from `main` leaves `pr-preview/` alone. A pull request from a fork
gets no preview, since its token cannot push here.

## Where the design lives

- [`CONTEXT.md`](CONTEXT.md) is the glossary, and nothing else. Use its words
  in code, prose and the UI. When a term settles or changes, update it in the
  same pull request.
- [`docs/adr/`](docs/adr/) records decisions and why. If a change overturns
  one, amend the record in the same pull request.

## Prose

Run prose through the [stop-slop](https://github.com/hardikpandya/stop-slop)
skill before it lands: the Markdown in the repo, the ADRs and the glossary
included, the guide's pages, issues, pull requests and commit messages. If
its rules clash with a term from `CONTEXT.md` or with wording the repo keeps
exact, such as the invariants under _Checks_, keep the term and the wording.
Install the skill in your own skills folder, as its README says.

## Tracking progress

The work is planned in GitHub issues, and `gh issue list` shows what is open.

- Every pull request closes or references an issue: `Closes #n` in its
  description when it finishes the issue, `#n` alone when it does not.
- Every issue belongs to a milestone.
- Labels are `simulator`, `site`, `preset` and `process`.
- A milestone's issues are opened when the milestone starts, not up front, so
  each is written knowing what the milestones before it found.

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
and merging deploys. pre-commit.ci runs the hooks on the pull request and
pushes a commit with whatever they fix, so pull before you push again.
