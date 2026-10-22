import pytest

from pep848_sim.widget.request import runs
from test_run import digest, records

# test_run's FIXED workload and settings, as a widget sends them.
FIXED = """{
    "workload": {
        "churn": {
            "cycle_share": "1/4", "cycle_size": 3, "lifetime_mean": 200,
            "long_share": "1/20", "long_lifetimes": [100, 1000]
        },
        "structures": [
            {"shape": {"chains": 16}, "size": 1000, "root": "module",
             "lifetime": null, "rebuild_interval": null, "build_churn": 0},
            {"shape": "tree", "size": 100, "root": "frame",
             "lifetime": 400, "rebuild_interval": 1000, "build_churn": 1}
        ],
        "seed": 848
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
        ('"tree"', '"list"', "no shape 'list'"),
        ('"module"', '"global"', "no root 'global'"),
    ],
)
def test_a_request_the_simulator_cannot_run_names_what_it_cannot(
    old: str, new: str, message: str
) -> None:
    request = FIXED.replace(old, new)

    with pytest.raises(ValueError, match=message):
        runs(request)
