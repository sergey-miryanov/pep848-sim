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


def run(name: str) -> tuple[list[Record], list[Record]]:
    """The step's runs, legacy first, as the widget asks the worker for them."""
    return _runs(json.dumps(STEPS[name]["request"], sort_keys=True))


# Steps share requests, and the widget keeps a run it has drawn (#135).
@cache
def _runs(request: str) -> tuple[list[Record], list[Record]]:
    legacy, incremental = runs(request)
    return (
        [record for part in legacy for record in part],
        [record for part in incremental for record in part],
    )


def work(record: Record) -> int:
    return record.marked + record.survived + record.freed


def figures(records: list[Record]) -> Figures:
    return Figures().add(records)


def thousands(count: int) -> float:
    """A count in thousands to one decimal, as the widget writes 90.2K, or an
    object count in MB, as it writes 1.1 MB."""
    return round(count / 100) / 10


def heap(record: Record) -> int:
    return sum(record.spaces_before)


def work_per_mb(records: list[Record]) -> int:
    """Work per MB to a whole number, as the widget writes 284."""
    per_mb = figures(records).work_per_mb
    assert per_mb is not None
    return round(per_mb)


def yield_percent(records: list[Record]) -> float:
    """Yield to a tenth of a point, as the widget writes 45.9%."""
    examined = figures(records).yield_
    assert examined is not None
    return round(examined * 1000) / 10


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


def test_every_chapter_has_steps() -> None:
    assert all(chapter["steps"] for chapter in GUIDE["chapters"])


def test_without_cycles_the_two_heaps_differ_by_start_ups_garbage_alone() -> None:
    legacy, incremental = run("why-a-cycle-collector-1")
    assert [r.clock for r in legacy] == [r.clock for r in incremental]
    assert all(
        0 <= heap(i) - heap(lg) <= 13 for lg, i in zip(legacy, incremental, strict=True)
    )


def test_reference_counting_holds_the_heap_below_1_2_mb() -> None:
    legacy, _ = run("why-a-cycle-collector-2")
    assert max(map(heap, legacy)) < 1_200
    assert round(legacy[-1].clock / 1000) == 21


def test_young_collections_hold_the_garbage_between_1_0_and_1_2_mb() -> None:
    _, incremental = run("why-a-cycle-collector-3")
    garbage = [heap(r) - r.reachable_before for r in before_shutdown(incremental)]
    clocks = [r.clock for r in before_shutdown(incremental)]
    widening = garbage[: clocks.index(12_000) + 1]
    assert widening == sorted(widening)
    assert thousands(widening[-1]) == 1.0
    assert thousands(max(garbage)) == 1.2
    assert all(g >= 1_000 for g in garbage[clocks.index(12_000) :])


def test_every_gen_0_collection_frees_cycles() -> None:
    legacy, _ = run("why-a-cycle-collector-4")
    gen0 = [r for r in legacy if r.kind == "gen 0"]
    assert gen0
    assert all(r.freed for r in gen0)


def test_early_collections_keep_two_or_three_objects_for_each_they_free() -> None:
    legacy, incremental = run("why-a-cycle-collector-5")
    for r in legacy:
        if 1_000 <= r.clock <= 5_000:
            assert 1.9 < r.survived / r.freed < 3.5
    assert yield_percent(legacy) == 45.9
    assert yield_percent(incremental) == 70.5


def test_the_incremental_collector_looks_later_and_keeps_less() -> None:
    legacy, incremental = run("why-a-cycle-collector-6")
    first = next(r for r in incremental if work(r))
    assert first.clock == 11_000
    for clock in (19_000, 21_000):
        [young] = [r for r in before_shutdown(incremental) if r.clock == clock]
        assert young.freed
        assert young.survived == young.marked == 0
    assert work_per_mb(legacy) == 284
    assert work_per_mb(incremental) == 228


def test_only_gen_1_and_gen_2_collections_fill_the_old_generation() -> None:
    legacy, _ = run("the-legacy-collector-1")
    # The old generation is the legacy collector's third space.
    for a, b in pairwise(before_shutdown(legacy)):
        assert b.spaces_before[2] <= a.spaces_after[2]
    assert max(r.spaces_after[2] for r in legacy) > 85_000


def test_gen_0_and_gen_1_collections_examine_the_graph_as_it_loads() -> None:
    legacy, _ = run("the-legacy-collector-2")
    loading = [r for r in legacy if 16_000 <= r.clock <= 124_000]
    assert {work(r) for r in loading if r.kind == "gen 0"} == {806, 807}
    gen1 = [r for r in loading if r.kind == "gen 1"]
    assert [r.clock for r in gen1] == list(range(24_000, 124_000, 12_000))
    assert [round(work(r), -2) for r in gen1] == [8_000] + [9_700] * (len(gen1) - 1)


def test_the_gen_2_collection_takes_the_whole_graph_at_133_mb() -> None:
    legacy, incremental = run("the-legacy-collector-3")
    [gen2] = [r for r in legacy if r.kind == "gen 2"]
    assert (gen2.clock, work(gen2)) == (133_000, 91_445)
    assert legacy.index(gen2) == 132
    assert thousands(figures(legacy).peak_work) == 91.4
    assert thousands(figures(incremental).peak_work) == 1.6


def test_the_quarter_holds_gen_2_collections_back_once_the_graph_has_loaded() -> None:
    legacy, _ = run("the-legacy-collector-4")
    gen2 = [r for r in legacy if r.kind == "gen 2"]
    assert [r.clock for r in gen2] == [37_000, 74_000, 111_000]
    assert [work(r) for r in gen2] == sorted(map(work, gen2))
    assert figures(legacy).gen2_collections == 3


def test_the_incremental_collectors_bars_stand_no_taller_than_a_young_ones() -> None:
    _, incremental = run("the-legacy-collector-5")
    old = [r for r in before_shutdown(incremental) if r.kind == "old"]
    young = [r for r in before_shutdown(incremental) if r.kind == "young"]
    assert max(map(work, old)) == max(map(work, young)) == 1_613


def test_visited_stays_empty_until_the_young_collection_at_11_mb() -> None:
    _, incremental = run("the-young-generation-1")
    first = next(record for record in incremental if work(record))
    assert (first.kind, first.clock) == ("young", 11_000)


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
    assert young == [11_000, 13_000, 15_000, 17_000]


def test_work_per_mb_reads_192_against_136() -> None:
    legacy, incremental = run("the-young-generation-5")
    assert work_per_mb(legacy) == 192
    assert work_per_mb(incremental) == 136


def test_at_the_peps_threshold0_the_run_ends_before_a_young_collection() -> None:
    legacy, incremental = run("the-young-generation-6")
    assert not any(map(work, before_shutdown(incremental)))
    assert not any(record.kind == "gen 1" for record in legacy)
    assert work_per_mb(incremental) == 82


def test_at_120_kb_a_gen_2_collection_fits_the_run() -> None:
    legacy, incremental = run("the-young-generation-7")
    [gen2] = [r.clock for r in legacy if r.kind == "gen 2"]
    assert round(gen2 / 1000) == 16
    gen1 = [r.clock for r in legacy if r.kind == "gen 1" and r.clock < gen2]
    assert {b - a for a, b in pairwise(gen1)} == {1_440}
    assert Figures().add(incremental).sweeps == 0
    assert work_per_mb(legacy) == 249
    assert work_per_mb(incremental) == 136


def test_a_longer_aging_generation_lets_the_first_mb_alone_through() -> None:
    _, incremental = run("the-young-generation-8")
    [young] = [r for r in before_shutdown(incremental) if work(r)]
    assert (young.clock, young.kind, work(young), young.survived) == (
        21_000,
        "young",
        265,
        257,
    )


def old_generation(record: Record) -> int:
    """The incremental collector's pending and visited spaces, before the
    collection."""
    return record.spaces_before[2] + record.spaces_before[3]


def sweep_ends(records: list[Record]) -> list[int]:
    """The clocks of the collections that ended a sweep."""
    return [b.clock for a, b in pairwise(records) if b.sweep > a.sweep]


def test_the_old_generation_fills_and_empties_with_each_tree() -> None:
    _, incremental = run("the-old-generation-1")
    old = list(map(old_generation, before_shutdown(incremental)))
    peak = old.index(max(old))
    assert max(old) > 45_000
    assert min(old[peak:]) < 10_000


def test_sweeps_double_while_a_tree_grows() -> None:
    _, incremental = run("the-old-generation-2")
    assert figures(incremental).sweeps == 17
    assert sweep_ends(incremental)[:4] == [44_000, 64_000, 104_000, 128_000]


def test_old_collections_mark_about_1_850_each() -> None:
    _, incremental = run("the-old-generation-3")
    old = [r for r in before_shutdown(incremental) if r.kind == "old"]
    assert max(map(work, old)) == 1_886
    assert sum(r.marked for r in old) > 10 * sum(r.survived + r.freed for r in old)
    young = [r for r in before_shutdown(incremental) if r.kind == "young"]
    assert 0.8 < sum(r.marked for r in old) / sum(map(work, young)) < 1.25


def test_young_collections_lift_the_budget_and_old_ones_spend_it() -> None:
    _, incremental = run("the-old-generation-4")
    paced = [r for r in before_shutdown(incremental) if r.clock >= 44_000]
    assert max(r.work_to_do for r in paced if r.kind == "young") == 1_844
    # A sweep's last increment can overspend by a few of start-up's objects.
    assert all(-50 < r.work_to_do <= 0 for r in paced if r.kind == "old")


def test_the_legacy_collectors_tallest_bars_hold_gen_1_collections() -> None:
    legacy, incremental = run("the-old-generation-5")
    assert max(work(r) for r in legacy if r.kind == "gen 1") == 11_150
    [gen2] = [r for r in legacy if r.kind == "gen 2"]
    assert (gen2.clock, work(gen2)) == (266_000, 1_486)
    assert work_per_mb(legacy) == 867
    assert work_per_mb(incremental) == 654


def test_the_smallest_tree_runs_no_sweep() -> None:
    _, incremental = run("the-old-generation-6")
    assert figures(incremental).sweeps == 0


def test_at_the_largest_tree_gen_2_examines_all_of_it() -> None:
    legacy, incremental = run("the-old-generation-7")
    [gen2] = [r for r in legacy if r.kind == "gen 2"]
    assert (gen2.clock, work(gen2)) == (266_000, 54_060)
    assert work(gen2) > 4 * max(work(r) for r in legacy if r.kind == "gen 1")
    assert thousands(figures(legacy).peak_work) == 54.1
    assert thousands(figures(incremental).peak_work) == 1.8


def test_the_budget_holds_at_its_start_until_22_mb() -> None:
    _, incremental = run("the-work-budget-1")
    assert {r.work_to_do for r in incremental if r.clock < 22_000} == {-6_250}
    assert next(r for r in incremental if r.clock == 22_000).work_to_do > -6_250


def test_young_collections_pay_the_budget_back_before_the_first_sweep() -> None:
    _, incremental = run("the-work-budget-2")
    raising = [
        r for r in incremental if 22_000 <= r.clock <= 42_000 and r.kind == "young"
    ]
    assert [r.clock for r in raising] == list(range(22_000, 43_000, 4_000))
    assert [r.work_to_do for r in raising] == sorted(r.work_to_do for r in raising)
    assert raising[-2].work_to_do < 0 < raising[-1].work_to_do
    assert sweep_ends(incremental)[0] == 44_000
    assert figures(incremental).sweeps == 17


def test_a_larger_freed_credit_changes_nothing_here() -> None:
    assert run("the-work-budget-3") == run("the-work-budget-2")


def test_a_lower_start_puts_the_first_sweep_at_56_mb() -> None:
    _, incremental = run("the-work-budget-4")
    assert incremental[0].work_to_do == -12_500
    assert sweep_ends(incremental)[0] == 56_000
    assert figures(incremental).sweeps == 16


def test_a_start_at_zero_ends_the_first_sweep_at_24_mb() -> None:
    _, incremental = run("the-work-budget-5")
    assert sweep_ends(incremental)[0] == 24_000
    assert figures(incremental).sweeps == 20


def test_a_start_above_zero_buys_an_empty_sweep() -> None:
    _, incremental = run("the-work-budget-6")
    first = next(r for r in incremental if r.sweep)
    assert (first.clock, first.kind, first.work_to_do) == (4_000, "old", 0)
    assert figures(incremental).sweeps == 21


def trees_freed(records: list[Record]) -> list[tuple[int, int]]:
    return [(r.clock, r.freed) for r in before_shutdown(records) if r.freed > 50_000]


def test_old_collections_free_two_trees_with_parent_pointers() -> None:
    _, incremental = run("the-work-budget-7")
    assert trees_freed(incremental) == [(236_000, 52_487), (380_000, 52_487)]
    assert figures(incremental).sweeps == 8


def test_without_the_credit_the_second_comes_later() -> None:
    _, incremental = run("the-work-budget-8")
    assert [clock for clock, _ in trees_freed(incremental)] == [236_000, 468_000]
    assert figures(incremental).sweeps == 5


def peak_garbage(name: str) -> tuple[float, float]:
    legacy, incremental = run(name)
    return (
        thousands(figures(legacy).peak_uncollected_garbage),
        thousands(figures(incremental).peak_uncollected_garbage),
    )


def wpm(name: str) -> tuple[int, int]:
    legacy, incremental = run(name)
    return work_per_mb(legacy), work_per_mb(incremental)


def test_without_cycles_start_ups_trees_are_the_peak_garbage() -> None:
    assert peak_garbage("uncollected-garbage-and-peak-memory-1") == (0.8, 0.8)


def test_cycles_wait_for_shutdown_under_the_incremental_collector() -> None:
    _, incremental = run("uncollected-garbage-and-peak-memory-2")
    assert not any(map(work, before_shutdown(incremental)))
    assert peak_garbage("uncollected-garbage-and-peak-memory-2") == (0.8, 1.9)
    assert wpm("uncollected-garbage-and-peak-memory-2") == (229, 174)


def test_with_half_the_churn_cycles_half_waits() -> None:
    assert peak_garbage("uncollected-garbage-and-peak-memory-3") == (1.0, 10.1)


def test_a_smaller_young_generation_frees_the_cycles() -> None:
    assert peak_garbage("uncollected-garbage-and-peak-memory-4") == (0.8, 1.2)
    assert wpm("uncollected-garbage-and-peak-memory-4") == (284, 228)


def test_a_large_program_holds_less_garbage_under_the_incremental_collector() -> None:
    assert peak_garbage("uncollected-garbage-and-peak-memory-5") == (5.4, 1.2)
    assert wpm("uncollected-garbage-and-peak-memory-5") == (1_526, 818)


def increments(records: list[Record]) -> list[tuple[int, int]]:
    """The old collections that took more than a young collection moves in."""
    return [
        (r.clock, work(r))
        for r in before_shutdown(records)
        if r.kind == "old" and work(r) > 5_000
    ]


def test_each_increment_from_the_graphs_root_grows() -> None:
    _, incremental = run("a-large-increment-1")
    assert increments(incremental) == [
        (48_000, 8_409),
        (64_000, 14_862),
        (96_000, 27_764),
    ]


def test_the_largest_increment_passes_the_legacy_collectors_peak() -> None:
    legacy, incremental = run("a-large-increment-2")
    assert thousands(figures(legacy).peak_work) == 19.4
    assert thousands(figures(incremental).peak_work) == 27.8


def test_young_collections_pay_back_the_largest_increment() -> None:
    _, incremental = run("a-large-increment-3")
    after = [r for r in before_shutdown(incremental) if r.clock >= 96_000]
    assert after[0].work_to_do == -24_539
    young = [r.work_to_do for r in after if r.kind == "young"][:3]
    assert [b - a for a, b in pairwise([-24_539, *young])] == [3_226, 3_225, 3_226]


def test_half_the_graph_loads_before_the_third_increment() -> None:
    _, incremental = run("a-large-increment-4")
    assert increments(incremental) == [(48_000, 8_409), (64_000, 14_862)]
    assert thousands(figures(incremental).peak_work) == 14.9


def test_a_quarter_of_the_graph_forms_no_increment() -> None:
    _, incremental = run("a-large-increment-5")
    assert increments(incremental) == []
    assert thousands(figures(incremental).peak_work) == 3.2


def automatic(records: list[Record]) -> list[Record]:
    return [r for r in records if r.kind not in ("full", "shutdown")]


def test_each_loop_calls_gc_collect() -> None:
    for records in run("gc-collect-and-shutdown-1"):
        assert sum(r.kind == "full" for r in records) == 1_024


def test_the_runtime_starts_two_collections_before_the_loops() -> None:
    for records in run("gc-collect-and-shutdown-2"):
        assert [r.clock for r in automatic(records)] == [2_000, 4_000]
        assert figures(records).collections == 1_029


def test_the_calls_cost_the_same_under_either_collector() -> None:
    assert [thousands(w) for w in wpm("gc-collect-and-shutdown-3")] == [12.7, 12.6]


def test_a_fifth_of_what_the_incremental_collector_examines_is_rings() -> None:
    legacy, incremental = run("gc-collect-and-shutdown-4")
    assert yield_percent(legacy) == 5.5
    assert yield_percent(incremental) == 22.2


def test_peak_work_leaves_the_calls_out() -> None:
    legacy, incremental = run("gc-collect-and-shutdown-5")
    assert figures(legacy).peak_work == work(automatic(legacy)[0]) == 531
    assert figures(incremental).peak_work == 0


def test_shutdowns_second_collection_frees_the_tree() -> None:
    for records in run("gc-collect-and-shutdown-6"):
        shutdown = [r for r in records if r.kind == "shutdown"]
        assert [bool(r.freed) for r in shutdown] == [False, True, False]
        assert round(shutdown[0].clock / 1000) == 98
        assert thousands(sum(before_shutdown(records)[-1].spaces_after)) == 1.1
        assert sum(shutdown[-1].spaces_after) <= 1


def test_below_a_loops_build_the_runtime_collects_again() -> None:
    legacy, incremental = run("gc-collect-and-shutdown-7")
    assert len(automatic(legacy)) == 566
    assert sum(r.freed for r in automatic(legacy)) == 13
    assert sum(map(work, automatic(incremental))) == 971


def test_the_peps_thresholds_collect_every_2_mb() -> None:
    for records in run("tuning-1"):
        assert figures(records).collections == 102


def test_half_the_threshold0_doubles_the_collections_and_halves_each() -> None:
    _, incremental = run("tuning-2")
    _, at_2000 = run("tuning-1")
    assert figures(incremental).collections == 201
    young = [work(r) for r in incremental if r.kind == "young"]
    assert max(young) == 1_613
    assert max(work(r) for r in at_2000 if r.kind == "young") == 3_226


def test_peak_work_grows_and_leaps_for_the_legacy_collector() -> None:
    _, at_2000 = run("tuning-1")
    legacy, incremental = run("tuning-3")
    legacy_at_2000, _ = run("tuning-1")
    assert thousands(figures(at_2000).peak_work) == 3.2
    assert thousands(figures(incremental).peak_work) == 1.6
    assert thousands(figures(legacy_at_2000).peak_work) == 19.4
    assert thousands(figures(legacy).peak_work) == 91.4
    assert [r.clock for r in legacy if r.kind == "gen 2"] == [133_000]


def first_marking(records: list[Record]) -> int:
    """The clock of the first old collection that marks more than a few objects."""
    return next(r.clock for r in records if r.kind == "old" and r.marked > 100)


def test_a_longer_aging_generation_delays_the_marking() -> None:
    _, incremental = run("tuning-4")
    _, at_10 = run("tuning-1")
    first = next(r for r in incremental if r.kind == "young" and work(r))
    assert first.clock == 42_000
    assert (first_marking(incremental), first_marking(at_10)) == (68_000, 48_000)


def test_at_threshold1_2_two_gen_2_collections_fit_the_run() -> None:
    legacy, _ = run("tuning-5")
    kinds = [r.kind for r in legacy[:12]]
    assert kinds == ["gen 0", "gen 0", "gen 0", "gen 1"] * 3
    gen2 = [r for r in legacy if r.kind == "gen 2"]
    assert [(r.clock, work(r)) for r in gen2] == [(90_000, 63_248), (180_000, 91_445)]
    assert figures(legacy).gen2_collections == 2
