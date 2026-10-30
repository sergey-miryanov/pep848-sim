import json
from fractions import Fraction
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import CollectorSettings, Constants
from pep848_sim.presets import CREATE_GC_CYCLES
from pep848_sim.widget.request import Request, dump, expand, parse, runs
from pep848_sim.workload import WorkloadParameters
from test_run import PINNED, collector_settings, constants, digest, records, workloads

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
    assert digest(records(legacy)) == PINNED["fixed"]["legacy"]
    assert digest(records(incremental)) == PINNED["fixed"]["incremental"]


def test_the_fixed_request_is_the_one_its_digests_are_pinned_for() -> None:
    assert json.loads(FIXED) == PINNED["fixed"]["request"]


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
        ('"tree"', '{"own": 1}', "your shape's code is not text"),
        ('{"chains": 16}', '{"chains": 0}', "0 chains hold no objects"),
        ('"size": 100,', '"size": 0,', "a structure of 0 objects builds nothing"),
        ('"lifetime": 400', '"lifetime": -1', "a structure cannot live -1 kB"),
        (
            '"build_churn": 1,',
            '"build_churn": 1, "built_in_frame": true,',
            "a structure a frame holds is built in one already",
        ),
        (
            '"build_churn": 1',
            '"build_churn": -1',
            "a build cannot follow each object with -1 churn allocations",
        ),
        ('"build_churn": 1', '"build_churn": 0.5', "a build's churn of 0.5 is no"),
        ('"build_churn": 1', '"build_churn": "half"', "a build's churn of 'half' is"),
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
        ('"every": 50', '"every": 0', "a part of 0 records holds none"),
        ('"every": 50', '"every": -1', "a part of -1 records holds none"),
    ],
)
def test_a_request_the_simulator_cannot_run_names_what_it_cannot(
    old: str, new: str, message: str
) -> None:
    request = FIXED.replace(old, new)

    with pytest.raises(ValueError, match=message):
        runs(request)


@pytest.mark.parametrize("threshold1", [0, -1])
def test_a_request_runs_a_threshold1_below_1_under_both_collectors(
    threshold1: int,
) -> None:
    legacy, incremental = runs(
        FIXED.replace('"threshold1": 10', f'"threshold1": {threshold1}')
    )
    one = runs(FIXED.replace('"threshold1": 10', '"threshold1": 1'))[1]

    # The legacy collector takes it as given; the incremental one runs it as 1.
    assert digest(records(legacy)) != PINNED["fixed"]["legacy"]
    assert records(incremental) == records(one)


@pytest.mark.parametrize("flag", ["built_in_frame", "built_in_c"])
def test_a_request_from_before_a_flag_opens_and_is_written_with_it(flag: str) -> None:
    request = parse(FIXED)

    assert [getattr(s, flag) for s in request.workload.structures] == [False, False]
    written = json.loads(dump(request))["workload"]["structures"]
    assert [s[flag] for s in written] == [False, False]


def test_a_request_carries_its_constants_to_both_runs() -> None:
    request = json.loads(FIXED)
    request["constants"] = {
        "initial_work_budget": -1_000,
        "freed_credit": 2,
        "long_lived_ratio": "100",
        "real_object_size": 32,
    }

    legacy, incremental = runs(json.dumps(request))

    # -1,000 real objects of 32 B: 31.25 kB, rounded down.
    assert records(incremental)[0].work_to_do == -32
    # Gen 2 waits for 100 times what the last one left, so it runs once alone.
    assert [record.kind for record in records(legacy)].count("gen 2") == 1


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        (
            "freed_credit",
            -1,
            "a freed-credit multiplier of -1 takes work off the budget for each"
            " object an increment frees",
        ),
        ("long_lived_ratio", "-1/4", "a long-lived ratio of -1/4 falls under 0"),
        ("real_object_size", 0, "a real object of 0 B takes no room"),
        ("long_lived_ratio", None, "constants lacks 'long_lived_ratio'"),
        ("freed_credits", 2, "constants has no field 'freed_credits'"),
    ],
)
def test_a_request_refuses_constants_no_collector_could_run_by(
    name: str, value: Any, message: str
) -> None:
    request = json.loads(dump(parse(FIXED)))
    if value is None:
        del request["constants"][name]
    else:
        request["constants"][name] = value

    with pytest.raises(ValueError, match=message):
        parse(json.dumps(request))


def test_a_request_refuses_a_bad_link_of_its_own_shape_before_a_run_starts() -> None:
    code = "def links(i):\n    return [(0, i)] if i < 5 else [(i, i + 1)]\n"
    request = FIXED.replace('"tree"', json.dumps({"own": code}))

    with pytest.raises(ValueError, match=r"links\(5\) gives \(5, 6\)"):
        parse(request)


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
        Constants(),
    )


def test_a_request_that_names_a_preset_can_carry_constants() -> None:
    request = json.loads(PRESET)
    request["constants"] = {
        "initial_work_budget": 0,
        "freed_credit": 1,
        "long_lived_ratio": "1/2",
        "real_object_size": 128,
    }

    assert parse(json.dumps(request)).constants == Constants(0, 1, Fraction(1, 2), 128)


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


def test_a_request_that_names_a_preset_can_change_its_fields() -> None:
    request = json.loads(PRESET)
    request["changes"] = {
        "workload.churn.cycle_share": "1/10",
        "workload.structures.0.size": 7,
        "run_length": 4000,
    }

    parsed = parse(json.dumps(request))

    assert parsed.workload.churn.cycle_share == Fraction(1, 10)
    assert parsed.workload.structures[0].size == 7
    assert parsed.run_length == 4000
    assert parsed.workload.structures[1:] == CREATE_GC_CYCLES.workload.structures[1:]


@pytest.mark.parametrize(
    "path",
    [
        "workload.churn.cycle_size_mean",
        "workload.structures.9.size",
        "workload.structures.9",
        "workload.structures.x",
        "seed",
    ],
)
def test_a_request_changes_only_the_fields_its_preset_has(path: str) -> None:
    request = json.loads(PRESET)
    request["changes"] = {path: 1}

    with pytest.raises(ValueError, match="a preset's request has no field"):
        parse(json.dumps(request))


def test_expanding_a_request_spells_out_the_preset_it_names() -> None:
    expanded = json.loads(expand(PRESET))

    assert "preset" not in expanded
    assert expanded["constants"] == {
        "initial_work_budget": -100_000,
        "freed_credit": 2,
        "long_lived_ratio": "1/4",
        "real_object_size": 64,
    }
    assert parse(json.dumps(expanded)) == parse(PRESET)


@given(
    workloads(),
    collector_settings(),
    st.integers(min_value=0, max_value=600),
    st.integers(min_value=1, max_value=5),
    constants(),
)
def test_a_dumped_request_parses_back_to_itself(
    workload: WorkloadParameters,
    settings: CollectorSettings,
    run_length: int,
    every: int,
    constants: Constants,
) -> None:
    request = Request(workload, settings, run_length, every, constants)

    assert parse(dump(request)) == request
