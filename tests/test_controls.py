import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import Tree
from pep848_sim.widget.controls import Control, controls
from pep848_sim.widget.request import runs
from pep848_sim.workload import WorkloadParameters
from test_run import collector_settings, workloads

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
             "lifetime": null, "rebuild_interval": null, "build_churn": 0},
            {"shape": "tree", "size": 20000, "root": "frame",
             "lifetime": 40000, "rebuild_interval": 80000, "build_churn": 1}
        ],
        "seed": 848
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
) -> str:
    """The request a widget sends for these runs."""
    churn = parameters.churn
    return json.dumps(
        {
            "workload": {
                "churn": {
                    "cycle_share": str(churn.cycle_share),
                    "cycle_size": churn.cycle_size,
                    "lifetime_mean": churn.lifetime_mean,
                    "long_share": str(churn.long_share),
                    "long_lifetimes": list(churn.long_lifetimes),
                },
                "structures": [
                    {
                        "shape": (
                            "tree"
                            if isinstance(structure.shape, Tree)
                            else {"chains": structure.shape.width}
                        ),
                        "size": structure.size,
                        "root": structure.root,
                        "lifetime": structure.lifetime,
                        "rebuild_interval": structure.rebuild_interval,
                        "build_churn": structure.build_churn,
                    }
                    for structure in parameters.structures
                ],
                "seed": parameters.seed,
            },
            "settings": {
                "threshold0": settings.threshold0,
                "threshold1": settings.threshold1,
                "threshold2": settings.threshold2,
            },
            "run_length": run_length,
            "every": every,
        }
    )


def paths(parameters: WorkloadParameters) -> list[str]:
    """Every path a control can take in a request for this workload."""
    found = ["settings.threshold0", "workload.churn.cycle_share"]
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
)
def test_every_value_a_control_allows_makes_runs_that_start(
    data: st.DataObject,
    parameters: WorkloadParameters,
    settings: CollectorSettings,
    run_length: int,
    every: int,
) -> None:
    text = request(parameters, settings, run_length, every)
    path = data.draw(st.sampled_from(paths(parameters)))
    [control] = controls(text, [path])
    steps = (control.max - control.min) // control.step
    between = control.min + data.draw(st.integers(0, steps)) * control.step

    assert control.min <= control.value <= control.max
    for value in (control.min, between, control.max):
        for parts in runs(with_value(text, control, value)):
            next(parts, None)
