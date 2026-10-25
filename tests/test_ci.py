import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def leaves(recipe: str, justfile: str) -> list[str]:
    """The recipes `recipe` runs that run no others, in the order it runs them."""
    line = re.search(
        rf"^{re.escape(recipe)}(?: [^:\n]*)?:(?!=)(.*)$", justfile, re.MULTILINE
    )
    assert line is not None, recipe
    dependencies = line[1].split()
    if not dependencies:
        return [recipe]
    return [leaf for name in dependencies for leaf in leaves(name, justfile)]


def test_ci_runs_a_job_for_each_recipe_just_check_runs() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix = re.search(r"^ +recipe: \[(.*)\]$", workflow, re.MULTILINE)
    assert matrix is not None

    assert [name.strip() for name in matrix[1].split(",")] == leaves("check", justfile)
