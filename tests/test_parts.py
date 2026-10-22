"""The package's parts import one way, as CONTRIBUTING.md lays them out."""

import ast
from collections.abc import Iterator
from importlib.util import resolve_name
from pathlib import Path

import pytest

import pep848_sim

# The parts, lowest first. A module imports from its own part and the parts below
# it, never from one above.
PARTS = ("pep848_sim.collectors", "pep848_sim", "pep848_sim.widget")


def modules() -> dict[str, Path]:
    """Every module in the package, by name, each with its file."""
    root = Path(pep848_sim.__file__).parent
    found = {}
    for path in sorted(root.rglob("*.py")):
        names = path.relative_to(root.parent).with_suffix("").parts
        found[".".join(names[:-1] if names[-1] == "__init__" else names)] = path
    return found


MODULES = modules()


def part(module: str) -> int:
    """Where the part that holds a module, the innermost one, stands in PARTS."""
    holders = [
        name for name in PARTS if module == name or module.startswith(f"{name}.")
    ]
    return PARTS.index(max(holders, key=len))


def imports(module: str) -> Iterator[str]:
    """What a module imports, by full name: each module, and each name it takes
    from one, which names the module too when that name is a submodule."""
    path = MODULES[module]
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            source = resolve_name("." * node.level + (node.module or ""), package)
            yield from (f"{source}.{alias.name}" for alias in node.names)


def test_every_package_is_a_part() -> None:
    packages = {name for name, path in MODULES.items() if path.name == "__init__.py"}

    assert packages == set(PARTS)


@pytest.mark.parametrize("module", MODULES)
def test_a_module_imports_nothing_from_a_part_above_its_own(module: str) -> None:
    above = [
        name
        for name in imports(module)
        if name.partition(".")[0] == "pep848_sim" and part(name) > part(module)
    ]

    assert above == []
