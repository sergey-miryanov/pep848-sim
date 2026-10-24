"""PROTOTYPE, not for main (#153): write the stand-in's request and each preset's,
spelled out, to site/prototype-playground.json, for the playground prototype's
"Start from" select."""

import json
from pathlib import Path

from pep848_sim.presets import PRESETS
from pep848_sim.widget.request import expand

OUT = Path(__file__).parent.parent / "site" / "prototype-playground.json"
SETTINGS = {"threshold0": 2000, "threshold1": 10, "threshold2": 10}
# As the home page's entries ask.
EVERY = {
    "create_gc_cycles": 20,
    "json_loads": 1,
    "xml_etree_parse": 5,
    "async_tree_io_tg": 10,
    "connected_components": 5,
}
STAND_IN = {
    "workload": {
        "churn": {
            "cycle_share": "3/100",
            "cycle_size": 3,
            "lifetime_mean": 5,
            "long_share": "1/20",
            "long_lifetimes": [100, 1000],
        },
        "structures": [
            {
                "shape": {"chains": 16},
                "size": 8000,
                "root": "module",
                "lifetime": None,
                "rebuild_interval": None,
                "build_churn": 0,
                "full_collections": False,
            },
            {
                "shape": "tree",
                "size": 20000,
                "root": "frame",
                "lifetime": 40000,
                "rebuild_interval": 80000,
                "build_churn": 1,
                "full_collections": False,
            },
        ],
        "seed": 848,
        "shutdown": False,
    },
    "settings": SETTINGS,
    "run_length": 150000,
    "every": 5,
}

requests = {"stand-in": STAND_IN} | {
    name: json.loads(
        expand(json.dumps({"preset": name, "settings": SETTINGS, "every": EVERY[name]}))
    )
    for name in PRESETS
}
OUT.write_text(json.dumps(requests, indent=1) + "\n", newline="\n")
