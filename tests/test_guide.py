"""The guide's steps (site/guide.json, ADR 0020): each runs, marks parts the
widget has, and says what its runs show."""

import json
import re
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from pep848_sim.collectors.collector import Record
from pep848_sim.widget.figures import Figures
from pep848_sim.widget.request import expand, runs

SITE = Path(__file__).parent.parent / "site"
GUIDE: dict[str, Any] = json.loads((SITE / "guide.json").read_text(encoding="utf-8"))
# Each step by the name the widget's entry takes in the URL fragment.
STEPS: dict[str, dict[str, Any]] = {
    f"{chapter['id']}-{index}": step
    for chapter in GUIDE["chapters"]
    for index, step in enumerate(chapter.get("steps", []), 1)
}


def marks() -> set[str]:
    """The parts the widget can mark: each collector's panels, and its figures
    by the names site/gc-widget.js gives them."""
    widget = (SITE / "gc-widget.js").read_text(encoding="utf-8")
    figures = re.findall(r'\{ name: "(\w+)", label:', widget)
    assert figures
    panels = {
        f"{c}.{p}"
        for c in ("legacy", "incremental")
        for p in ("heap", "work", "budget")
    }
    return panels | {f"figure.{name}" for name in figures}


@cache
def run(name: str) -> tuple[list[Record], list[Record]]:
    """The step's runs, legacy first, as the widget asks the worker for them."""
    legacy, incremental = runs(json.dumps(STEPS[name]["request"]))
    return (
        [record for part in legacy for record in part],
        [record for part in incremental for record in part],
    )


def work(record: Record) -> int:
    return record.marked + record.survived + record.freed


def before_shutdown(records: list[Record]) -> list[Record]:
    return [record for record in records if record.kind != "shutdown"]


@pytest.mark.parametrize("name", list(STEPS))
def test_each_step_runs_and_marks_parts_the_widget_has(name: str) -> None:
    step = STEPS[name]
    assert step["title"]
    assert step["text"]
    expand(json.dumps(step["request"]))
    assert step["marks"]
    for mark in step["marks"]:
        assert mark["part"] in marks()
        assert mark["note"]


def test_each_chapter_without_steps_has_its_section_in_the_long_form() -> None:
    long = (SITE / "guide-long.html").read_text(encoding="utf-8")
    for chapter in GUIDE["chapters"]:
        if "steps" not in chapter:
            assert f'<section id="{chapter["id"]}">' in long


def test_the_young_generation_waits_12_mb_for_its_first_young_collection() -> None:
    _, incremental = run("the-young-generation-1")
    first = next(record for record in incremental if work(record))
    assert (first.kind, first.clock) == ("young", 12_000)


def test_json_loads_collections_free_a_sliver_before_shutdown() -> None:
    for records in run("the-young-generation-2"):
        examined = before_shutdown(records)
        freed = sum(record.freed for record in examined)
        assert 0 < freed < sum(map(work, examined)) / 50


def test_the_legacy_collector_examines_the_workers_objects_twice() -> None:
    legacy, _ = run("the-young-generation-3")
    builds = [r for r in legacy if r.kind == "gen 0" and r.clock <= 5_000]
    assert [r.clock for r in builds] == [1_000, 2_000, 3_000, 4_000, 5_000]
    assert all(work(r) > 100 for r in builds)
    gen1 = next(record for record in legacy if record.kind == "gen 1")
    assert (gen1.clock, work(gen1)) == (12_000, 1_145)


def test_the_incremental_collector_examines_them_once() -> None:
    _, incremental = run("the-young-generation-4")
    young = [r.clock for r in before_shutdown(incremental) if work(r)]
    assert young == [12_000, 14_000, 16_000]


def test_work_per_mb_reads_192_against_136() -> None:
    legacy, incremental = run("the-young-generation-5")
    assert round(Figures().add(legacy).work_per_mb) == 192
    assert round(Figures().add(incremental).work_per_mb) == 136


def test_at_the_peps_threshold0_the_run_ends_before_a_young_collection() -> None:
    legacy, incremental = run("the-young-generation-6")
    assert not any(map(work, before_shutdown(incremental)))
    assert not any(record.kind == "gen 1" for record in legacy)
    assert round(Figures().add(incremental).work_per_mb) == 82


def test_at_120_kb_a_gen_2_collection_fits_the_run() -> None:
    legacy, incremental = run("the-young-generation-7")
    [gen2] = [r.clock for r in legacy if r.kind == "gen 2"]
    assert round(gen2 / 1000) == 16
    gen1 = [r.clock for r in legacy if r.kind == "gen 1" and r.clock < gen2]
    assert {b - a for a, b in pairwise(gen1)} == {1_440}
    assert Figures().add(incremental).sweeps == 0
    assert round(Figures().add(legacy).work_per_mb) == 249
    assert round(Figures().add(incremental).work_per_mb) == 136


def test_a_longer_aging_generation_outlasts_the_run() -> None:
    _, incremental = run("the-young-generation-8")
    assert not any(map(work, before_shutdown(incremental)))
