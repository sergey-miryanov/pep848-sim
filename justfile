set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

_default:
    @just --list

# lint, typecheck and test: what CI gates on
check: lint typecheck test

# pytest, Hypothesis invariants included, with the coverage gate
test:
    pytest

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
