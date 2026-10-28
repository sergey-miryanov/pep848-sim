set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

_default:
    @just --list

# check-py, check-ts, test-js and test-pyodide: what CI gates on
check: check-py check-ts test-js test-pyodide

# lint, typecheck and test: the Python
check-py: lint typecheck test

# tsc over the site's JavaScript: the page's scripts and the tests, then the worker
check-ts:
    node node_modules/typescript/bin/tsc -p tsconfig.json
    node node_modules/typescript/bin/tsc -p tsconfig.worker.json

# Node's test runner over the widget's JavaScript
test-js:
    node --test "tests/*.test.js"

# the pinned runs' digests under Pyodide, in Node (ADR 0007)
test-pyodide:
    node --test tests/digests.pyodide.js

# pytest, Hypothesis invariants included, with the coverage gate
test *args:
    pytest {{args}}

# ruff's checker and formatter
lint:
    ruff check
    ruff format --check

# mypy and pyrefly, both strict
typecheck:
    mypy
    pyrefly check --min-severity=warn

# assemble _site/: the pages at the top, the rest of site/ and src/pep848_sim
# zipped as sim.zip in v/<commit>/; --keep REF keeps the folder the site at REF
# serves too
site *args:
    python tools/assemble_site.py {{args}}

# run site, then serve _site/ on http://localhost:8000
serve: site
    python -m http.server 8000 --bind 127.0.0.1 --directory _site

# print each preset's collections beside its benchmark's
compare:
    python tools/compare_presets.py

# write each preset's collections and its benchmark's workers' to tools/plot.json,
# then serve tools/plot.html, which draws them, on http://localhost:8001
plot:
    python tools/plot_presets.py
    python -m http.server 8001 --bind 127.0.0.1
