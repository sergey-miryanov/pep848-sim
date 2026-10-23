set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

_default:
    @just --list

# check-py, check-ts and test-js: what CI gates on
check: check-py check-ts test-js

# lint, typecheck and test: the Python
check-py: lint typecheck test

# tsc over the site's JavaScript: the page's scripts and the tests, then the worker
check-ts:
    node node_modules/typescript/bin/tsc -p tsconfig.json
    node node_modules/typescript/bin/tsc -p tsconfig.worker.json

# Node's test runner over the widget's JavaScript
test-js:
    node --test "tests/*.test.js"

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

# assemble _site/: copy site/, zip src/pep848_sim into _site/sim.zip
site:
    python tools/assemble_site.py

# run site, then serve _site/ on http://localhost:8000
serve: site
    python -m http.server 8000 --bind 127.0.0.1 --directory _site

# print each preset's collections beside its benchmark's
compare:
    python tools/compare_presets.py
