import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import CollectorSettings, Constants
from pep848_sim.presets import CREATE_GC_CYCLES
from pep848_sim.widget.controls import Control, controls
from pep848_sim.widget.request import Request, dump, expand, runs
from pep848_sim.workload import WorkloadParameters, geometric_thresholds
from test_run import collector_settings, constants, workloads
from test_workload import exact_thresholds

# The stand-in widget's request: a 150 MB run at the PEP's thresholds, with 8 MB
# of module globals and a 20 MB tree rebuilt every 80 MB, one churn allocation
# after each built object.
STAND_IN = """{
    "workload": {
        "churn": {
            "cycle_share": "3/100", "cycle_size": 3, "lifetime_mean": 5,
            "long_share": "1/20", "long_lifetimes": [100, 1000]
        },
        "structures": [
            {"shape": {"chains": 16}, "size": 8000, "root": "module",
             "lifetime": null, "rebuild_interval": null, "build_churn": 0,
             "full_collections": false},
            {"shape": "tree", "size": 20000, "root": "frame",
             "lifetime": 40000, "rebuild_interval": 80000, "build_churn": 1,
             "full_collections": false}
        ],
        "seed": 848,
        "shutdown": false
    },
    "settings": {"threshold0": 2000, "threshold1": 10, "threshold2": 10},
    "run_length": 150000,
    "every": 5
}"""


def test_threshold0_ranges_over_10_to_1000_collections_a_run() -> None:
    # 150,000 kB over 1,000 collections is 150 kB, which the 100 kB step rounds
    # up to 200; over 10 collections, 15,000 kB.
    assert controls(STAND_IN, ["settings.threshold0"]) == [
        Control("settings.threshold0", "threshold0", "kB", 2000, 200, 15_000, 100)
    ]


def test_the_collectors_other_settings_and_constants_range_about_the_peps() -> None:
    paths = [
        "settings.threshold1",
        "settings.threshold2",
        "constants.initial_work_budget",
        "constants.freed_credit",
        "constants.long_lived_ratio",
    ]

    assert controls(STAND_IN, paths) == [
        Control("settings.threshold1", "threshold1", "count", 10, 1, 40, 1),
        Control(
            "settings.threshold2", "threshold2 (legacy only)", "count", 10, 0, 40, 1
        ),
        Control(
            "constants.initial_work_budget",
            "Initial work budget (real objects)",
            "count",
            -100_000,
            -200_000,
            50_000,
            1_000,
        ),
        Control(
            "constants.freed_credit", "Freed-credit multiplier", "count", 2, 0, 10, 1
        ),
        Control(
            "constants.long_lived_ratio", "Long-lived ratio", "share", 250, 0, 1000, 1
        ),
    ]


@pytest.mark.parametrize(
    ("path", "value", "low", "high"),
    [
        ("settings.threshold1", 50, 1, 50),
        ("settings.threshold2", 60, 0, 60),
        ("settings.threshold2", -1, -1, 40),
        ("constants.initial_work_budget", -300_000, -300_000, 50_000),
        ("constants.initial_work_budget", 80_000, -200_000, 80_000),
        ("constants.freed_credit", 12, 0, 12),
        ("constants.long_lived_ratio", "3/2", 0, 1500),
    ],
)
def test_a_collector_control_takes_in_the_requests_own_value(
    path: str, value: int | str, low: int, high: int
) -> None:
    values = json.loads(expand(STAND_IN))
    group, name = path.split(".")
    values[group][name] = value

    [control] = controls(json.dumps(values), [path])

    assert (control.min, control.max) == (low, high)
    assert control.min <= control.value <= control.max


def test_cycle_share_ranges_up_to_half_the_churn_in_thousandths() -> None:
    assert controls(STAND_IN, ["workload.churn.cycle_share"]) == [
        Control(
            "workload.churn.cycle_share",
            "Churn that starts a cycle",
            "share",
            30,
            0,
            500,
            1,
        )
    ]


def test_the_churn_lifetime_mean_ranges_up_to_1000_kb_by_the_kb() -> None:
    assert controls(STAND_IN, ["workload.churn.lifetime_mean"]) == [
        Control(
            "workload.churn.lifetime_mean", "Churn lifetime mean", "kB", 5, 1, 1000, 1
        )
    ]


def test_the_longest_churn_lifetime_mean_builds_the_exact_thresholds() -> None:
    [control] = controls(STAND_IN, ["workload.churn.lifetime_mean"])

    assert geometric_thresholds(control.max) == exact_thresholds(control.max)


def test_a_repeating_structures_size_stops_where_its_build_fills_its_interval() -> None:
    # Each built object takes 1 kB and one churn allocation another: 40,000
    # objects fill 80,000 kB.
    assert controls(STAND_IN, ["workload.structures.1.size"]) == [
        Control(
            "workload.structures.1.size", "Tree size", "kB", 20_000, 100, 40_000, 100
        )
    ]


def test_a_structure_never_rebuilt_stops_where_its_build_fills_the_run() -> None:
    assert controls(STAND_IN, ["workload.structures.0.size"]) == [
        Control(
            "workload.structures.0.size", "Chains size", "kB", 8000, 1000, 150_000, 1000
        )
    ]


def test_a_rebuild_interval_starts_at_its_structures_build() -> None:
    # 20,000 objects and 20,000 churn allocations after them.
    assert controls(STAND_IN, ["workload.structures.1.rebuild_interval"]) == [
        Control(
            "workload.structures.1.rebuild_interval",
            "Tree rebuild interval",
            "kB",
            80_000,
            40_000,
            150_000,
            1000,
        )
    ]


def test_a_structure_that_outgrows_the_run_keeps_its_size_in_range() -> None:
    short = json.dumps(json.loads(STAND_IN) | {"run_length": 4000})

    assert controls(short, ["workload.structures.0.size"]) == [
        Control("workload.structures.0.size", "Chains size", "kB", 8000, 10, 8000, 10)
    ]


def test_a_rebuild_interval_that_outlasts_the_run_stays_in_range() -> None:
    short = json.dumps(json.loads(STAND_IN) | {"run_length": 60_000})

    assert controls(short, ["workload.structures.1.rebuild_interval"]) == [
        Control(
            "workload.structures.1.rebuild_interval",
            "Tree rebuild interval",
            "kB",
            80_000,
            40_000,
            80_000,
            100,
        )
    ]


@pytest.mark.parametrize(
    ("path", "refusal"),
    [
        ("workload.seed", "no control 'workload.seed'"),
        ("workload.structures.x.size", "no control 'workload.structures.x.size'"),
        ("workload.structures.2.size", "no structure 2"),
        ("workload.structures.0.rebuild_interval", "structure 0 is never rebuilt"),
    ],
)
def test_a_path_with_no_control_is_refused(path: str, refusal: str) -> None:
    with pytest.raises(ValueError, match=f"^{refusal}$"):
        controls(STAND_IN, [path])


def request(
    parameters: WorkloadParameters,
    settings: CollectorSettings,
    run_length: int,
    every: int,
    constants: Constants,
) -> str:
    """The request a widget sends for these runs."""
    return dump(Request(parameters, settings, run_length, every, constants))


def paths(parameters: WorkloadParameters) -> list[str]:
    """Every path a control can take in a request for this workload."""
    found = [
        "settings.threshold0",
        "settings.threshold1",
        "settings.threshold2",
        "constants.initial_work_budget",
        "constants.freed_credit",
        "constants.long_lived_ratio",
        "workload.churn.cycle_share",
        "workload.churn.lifetime_mean",
    ]
    for i, structure in enumerate(parameters.structures):
        found.append(f"workload.structures.{i}.size")
        if structure.rebuild_interval is not None:
            found.append(f"workload.structures.{i}.rebuild_interval")
    return found


def with_value(request: str, control: Control, value: int) -> str:
    """The request with the control set to a value, as the widget sets it."""
    values = json.loads(request)
    *keys, last = control.path.split(".")
    target: Any = values
    for key in keys:
        target = target[int(key)] if isinstance(target, list) else target[key]
    target[last] = f"{value}/1000" if control.unit == "share" else value
    return json.dumps(values)


@given(
    st.data(),
    workloads(),
    collector_settings(),
    st.integers(min_value=0, max_value=600),
    st.integers(min_value=1, max_value=5),
    constants(),
)
def test_every_value_a_control_allows_makes_runs_that_start(
    data: st.DataObject,
    parameters: WorkloadParameters,
    settings: CollectorSettings,
    run_length: int,
    every: int,
    constants: Constants,
) -> None:
    text = request(parameters, settings, run_length, every, constants)
    path = data.draw(st.sampled_from(paths(parameters)))
    [control] = controls(text, [path])
    steps = (control.max - control.min) // control.step
    between = control.min + data.draw(st.integers(0, steps)) * control.step

    assert control.min <= control.value <= control.max
    for value in (control.min, between, control.max):
        for parts in runs(with_value(text, control, value)):
            next(parts, None)


def test_a_control_reads_the_preset_a_request_names() -> None:
    request = json.dumps(
        {
            "preset": "create_gc_cycles",
            "settings": {"threshold0": 2000, "threshold1": 10, "threshold2": 10},
            "every": 20,
        }
    )
    rings = CREATE_GC_CYCLES.workload.structures[2]
    assert rings.rebuild_interval is not None

    [control] = controls(request, ["workload.structures.2.size"])

    # A build without churn fits in the rebuild interval.
    assert control == Control(
        "workload.structures.2.size",
        "Rings size",
        "kB",
        rings.size,
        1,
        rings.rebuild_interval,
        1,
    )
