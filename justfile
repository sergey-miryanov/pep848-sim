set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

_default:
    @just --list

# check-py and check-ts: what CI gates on
check: check-py check-ts

# lint, typecheck and test: the Python
check-py: lint typecheck test

# tsc over the site's JavaScript: the page's scripts, then the worker
check-ts:
    node node_modules/typescript/bin/tsc -p tsconfig.json
    node node_modules/typescript/bin/tsc -p tsconfig.worker.json

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
    pyrefly check

# assemble _site/: copy site/, zip src/pep848_sim into _site/sim.zip
site:
    python tools/assemble_site.py

# run site, then serve _site/ on http://localhost:8000
serve: site
    python -m http.server 8000 --bind 127.0.0.1 --directory _site
