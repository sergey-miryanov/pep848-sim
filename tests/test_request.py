import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.presets import CREATE_GC_CYCLES
from pep848_sim.widget.request import Request, dump, expand, parse, runs
from pep848_sim.workload import WorkloadParameters
from test_run import collector_settings, digest, records, workloads

# test_run's FIXED workload and settings, as a widget sends them.
FIXED = """{
    "workload": {
        "churn": {
            "cycle_share": "1/4", "cycle_size": 3, "lifetime_mean": 200,
            "long_share": "1/20", "long_lifetimes": [100, 1000]
        },
        "structures": [
            {"shape": {"chains": 16}, "size": 1000, "root": "module",
             "lifetime": null, "rebuild_interval": null, "build_churn": 0,
             "full_collections": false},
            {"shape": "tree", "size": 100, "root": "frame",
             "lifetime": 400, "rebuild_interval": 1000, "build_churn": 1,
             "full_collections": false}
        ],
        "seed": 848,
        "shutdown": false
    },
    "settings": {"threshold0": 20, "threshold1": 10, "threshold2": 10},
    "run_length": 20000,
    "every": 50
}"""


def test_a_request_runs_the_legacy_collector_then_the_incremental_one() -> None:
    legacy, incremental = runs(FIXED)

    # The digests test_run pins for the same workload.
    assert digest(records(legacy)) == "8eb3fc9dd9e3d903"
    assert digest(records(incremental)) == "c679a9492b62551a"


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('"seed": 848', '"seed": 848, "seeds": 1', "workload has no field 'seeds'"),
        (',\n    "every": 50', "", "request lacks 'every'"),
        (',\n        "shutdown": false', "", "workload lacks 'shutdown'"),
        ('"tree"', '"list"', "no shape 'list'"),
        ('"tree"', '{"rings": 0}', "a ring of 0 objects holds none"),
        ('"tree"', '{"hierarchy": 0}', "a hierarchy of 0 branches ends at its root"),
        ('"tree"', '{"graph": -1}', "a node cannot bring -1 edges"),
        ('"module"', '"global"', "no root 'global'"),
        ('{"chains": 16}', '{"chains": 0}', "0 chains hold no objects"),
        ('"size": 100,', '"size": 0,', "a structure of 0 objects builds nothing"),
        ('"lifetime": 400', '"lifetime": -1', "a structure cannot live -1 kB"),
        (
            '"build_churn": 1',
            '"build_churn": -1',
            "a build cannot follow each object with -1 churn allocations",
        ),
        ('"1/4"', '"5/4"', "a cycle share of 5/4 lies outside 0 to 1"),
        ('"cycle_size": 3', '"cycle_size": 0', "a cycle of 0 objects holds none"),
        (
            '"lifetime_mean": 200',
            '"lifetime_mean": 0',
            "a churn lifetime mean of 0 kB falls under 1 kB",
        ),
        ('"1/20"', '"-1/20"', "a long share of -1/20 lies outside 0 to 1"),
        (
            "[100, 1000]",
            "[1000, 100]",
            "long lifetimes cannot run from 1000 kB to 100 kB",
        ),
        ("[100, 1000]", "[0, 100]", "long lifetimes cannot run from 0 kB to 100 kB"),
        (
            '"threshold0": 20',
            '"threshold0": 0',
            "a threshold0 of 0 kB falls under 1 kB",
        ),
        (
            '"threshold1": 10',
            '"threshold1": 0',
            "a threshold1 of 0 leaves the incremental collector no aging space",
        ),
    ],
)
def test_a_request_the_simulator_cannot_run_names_what_it_cannot(
    old: str, new: str, message: str
) -> None:
    request = FIXED.replace(old, new)

    with pytest.raises(ValueError, match=message):
        runs(request)


# A request that names a preset, as a widget sends it.
PRESET = """{
    "preset": "create_gc_cycles",
    "settings": {"threshold0": 2000, "threshold1": 10, "threshold2": 10},
    "every": 50
}"""


def test_a_request_can_name_a_preset_for_its_workload_and_run_length() -> None:
    assert parse(PRESET) == Request(
        CREATE_GC_CYCLES.workload,
        CollectorSettings(),
        CREATE_GC_CYCLES.run_length,
        50,
    )


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('"create_gc_cycles"', '"json_dumps"', "no preset 'json_dumps'"),
        ('"every": 50', '"every": 50, "seed": 1', "request has no field 'seed'"),
        (',\n    "every": 50', "", "request lacks 'every'"),
    ],
)
def test_a_request_that_names_a_preset_holds_its_settings_and_no_workload(
    old: str, new: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse(PRESET.replace(old, new))


def test_expanding_a_request_spells_out_the_preset_it_names() -> None:
    expanded = json.loads(expand(PRESET))

    assert "preset" not in expanded
    assert parse(json.dumps(expanded)) == parse(PRESET)


@given(
    workloads(),
    collector_settings(),
    st.integers(min_value=0, max_value=600),
    st.integers(min_value=1, max_value=5),
)
def test_a_dumped_request_parses_back_to_itself(
    workload: WorkloadParameters,
    settings: CollectorSettings,
    run_length: int,
    every: int,
) -> None:
    request = Request(workload, settings, run_length, every)

    assert parse(dump(request)) == request
