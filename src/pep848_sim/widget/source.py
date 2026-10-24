"""A workload's source: the playground's workload, run length, collector settings
and constants, written as Python (ADR 0015). The source sets `churn`, `structures`
and `run_length`, and may set `settings`, `constants`, `seed` and `shutdown`, with
the names below besides the builtins. A shape of the reader's own is a function the
source defines, or code as text, either of which `Own` takes. A function's text
alone goes into the request, so it sees only i and what it imports itself.
"""

import ast
import textwrap
import traceback
from fractions import Fraction
from types import FunctionType
from typing import get_args

from pep848_sim.collectors.collector import CollectorSettings, Constants
from pep848_sim.structures import (
    Chains,
    Graph,
    Hierarchy,
    Own,
    Rings,
    Root,
    Shape,
    StructureParameters,
    Tree,
)
from pep848_sim.workload import ChurnParameters, WorkloadParameters

# The file name a workload's source runs under, which finds its lines in a
# traceback.
_FILE = "<your workload>"
# The seed of a workload whose source sets none, as every preset's.
_SEED = 848
# The constants of a workload whose source sets none, and those it leaves out.
_CONSTANTS = Constants()

type Share = str | int | float | Fraction


def read(text: str) -> tuple[WorkloadParameters, CollectorSettings, int, Constants]:
    """The workload, collector settings, run length and constants the source sets."""
    try:
        tree = ast.parse(text, _FILE)
    except SyntaxError as error:
        raise ValueError(f"line {error.lineno} of your workload: {error.msg}") from None
    namespace = _names(text, tree)
    try:
        exec(compile(tree, _FILE, "exec"), namespace)
    except Exception as error:
        raise ValueError(_raised(error)) from None
    churn = _set(namespace, "churn", ChurnParameters, "Churn(...)")
    structures = _set(namespace, "structures", list, "a list of Structure(...)")
    for structure in structures:
        if not isinstance(structure, StructureParameters):
            raise ValueError(f"structures holds {structure!r}, not a Structure(...)")
    run_length = _set(namespace, "run_length", int, "a whole number of kB")
    if run_length < 1:
        raise ValueError(f"a run_length of {run_length} kB allocates nothing")
    settings = _set(
        namespace, "settings", CollectorSettings, "Settings(...)", CollectorSettings()
    )
    constants = _set(namespace, "constants", Constants, "Constants(...)", _CONSTANTS)
    seed = _set(namespace, "seed", int, "a whole number", _SEED)
    shutdown = _set(namespace, "shutdown", bool, "True or False", False)
    workload = WorkloadParameters(churn, tuple(structures), seed, shutdown)
    return workload, settings, run_length, constants


def _names(text: str, tree: ast.Module) -> dict[str, object]:
    """What the source sees besides the builtins: the shapes, and a function for
    a structure, the churn, the collector settings and the constants."""
    lines = text.splitlines()
    # Each function the source defines without a decorator, by its first line.
    defined = {
        node.lineno: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and not node.decorator_list
    }

    def own(shape: object) -> Own:
        """A shape of the reader's own: a function the source defines with def,
        or code as text that defines links(i)."""
        if isinstance(shape, str):
            return Own(shape)
        first = 0
        if isinstance(shape, FunctionType) and shape.__code__.co_filename == _FILE:
            first = shape.__code__.co_firstlineno
        node = defined.get(first)
        if node is None:
            raise ValueError(
                "Own takes a function your workload defines with def, or code as text"
            )
        return Own(_text(lines, first, node), line=first)

    return {
        "Chains": Chains,
        "Tree": Tree,
        "Hierarchy": Hierarchy,
        "Graph": Graph,
        "Rings": Rings,
        "Own": own,
        "Structure": _structure,
        "Churn": _churn,
        "Settings": CollectorSettings,
        "Constants": _constants,
    }


def _text(
    lines: list[str], first: int, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> str:
    """A function's text in the source, from its first line through the last line
    of its body, the comments that follow it in its body included."""
    indent = _indent(lines[node.lineno - 1])
    end = node.end_lineno or node.lineno
    while end < len(lines) and (not lines[end].strip() or _indent(lines[end]) > indent):
        end += 1
    while not lines[end - 1].strip():
        end -= 1
    return textwrap.dedent("\n".join(lines[first - 1 : end])) + "\n"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _structure(
    shape: Shape,
    size: int,
    *,
    root: Root = "frame",
    lifetime: int | None = None,
    rebuild_interval: int | None = None,
    build_churn: int = 0,
    full_collections: bool = False,
) -> StructureParameters:
    """A structure, as `Structure(Tree(), size=1_000, root="frame")` sets one."""
    if not isinstance(shape, get_args(Shape.__value__)):
        raise ValueError(
            f"{shape!r} is no shape: Chains(...), Tree(), Hierarchy(...), Graph(...),"
            " Rings(...) or Own(...) gives one"
        )
    return StructureParameters(
        shape, size, root, lifetime, rebuild_interval, build_churn, full_collections
    )


def _churn(
    *,
    lifetime_mean: int,
    cycle_share: Share = 0,
    cycle_size: int = 2,
    long_share: Share = 0,
    long_lifetimes: tuple[int, int] = (1, 1),
) -> ChurnParameters:
    """The churn, as `Churn(lifetime_mean=5, cycle_share="3/100")` sets it. A share
    is a fraction, as text such as "3/100", or a number."""
    low, high = long_lifetimes
    return ChurnParameters(
        _share(cycle_share), cycle_size, lifetime_mean, _share(long_share), (low, high)
    )


def _constants(
    *,
    initial_work_budget: int = _CONSTANTS.initial_work_budget,
    freed_credit: int = _CONSTANTS.freed_credit,
    long_lived_ratio: Share = _CONSTANTS.long_lived_ratio,
    real_object_size: int = _CONSTANTS.real_object_size,
) -> Constants:
    """The collector constants and the real object's size, as
    `Constants(freed_credit=4)` sets them, the rest at their defaults. The
    long-lived ratio is a share, as the churn's are."""
    return Constants(
        initial_work_budget, freed_credit, _share(long_lived_ratio), real_object_size
    )


def _share(share: Share) -> Fraction:
    # A float as written, so 0.03 is 3/100, not the binary fraction nearest it.
    return Fraction(str(share)) if isinstance(share, float) else Fraction(share)


def _set[T](
    namespace: dict[str, object],
    name: str,
    kind: type[T],
    what: str,
    default: T | None = None,
) -> T:
    """The value the source sets `name` to, which must be `what`, or the default
    of a source that sets none."""
    value = namespace.get(name, default)
    if value is None:
        raise ValueError(f"your workload sets no {name}")
    # A bool is an int to isinstance, but no run length or seed.
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
        raise ValueError(f"your workload sets {name} to {value!r}, not {what}")
    return value


def _raised(error: Exception) -> str:
    """What the source raised as it ran, and its line: a refusal in the
    simulator's own words, or what went wrong in the reader's."""
    line = [
        frame.lineno
        for frame in traceback.extract_tb(error.__traceback__)
        if frame.filename == _FILE
    ][-1]
    if type(error) is ValueError:
        return f"line {line} of your workload: {error}"
    return f"your workload raised {type(error).__name__} at line {line}: {error}"
