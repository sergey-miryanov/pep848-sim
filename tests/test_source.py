import json
from pathlib import Path

import pytest

from pep848_sim.collectors.collector import CollectorSettings
from pep848_sim.structures import Own
from pep848_sim.widget.request import dump, parse

FIXTURES = Path(__file__).parent / "fixtures"

# What every source below needs besides its structures.
CHURN = "churn = Churn(lifetime_mean=5)\nrun_length = 1000\n"


def request(source: str) -> str:
    return json.dumps({"source": source, "every": 5})


def own(source: str) -> Own:
    """The shape of the source's one structure, a shape of its own."""
    shape = parse(request(CHURN + source)).workload.structures[0].shape
    assert isinstance(shape, Own)
    return shape


def test_a_source_reads_back_as_the_request_the_page_wrote_it_from() -> None:
    # tests/source.test.js writes the same source from the same request.
    expected = json.loads((FIXTURES / "source.json").read_text(encoding="utf-8"))
    source = (FIXTURES / "source.txt").read_text(encoding="utf-8")

    read = json.loads(dump(parse(request(source))))

    # The page renames a function whose name another took.
    structures = expected["workload"]["structures"]
    for i, renamed in ((7, "def links_2"), (8, "def churn_2")):
        structures[i]["shape"]["own"] = renamed + structures[i]["shape"]["own"][9:]
    assert read == expected


def test_a_source_that_sets_no_settings_seed_or_shutdown_takes_the_defaults() -> None:
    read = parse(request(CHURN + "structures = []\n"))

    assert read.settings == CollectorSettings()
    assert (read.workload.seed, read.workload.shutdown) == (848, False)
    assert read.run_length == 1000


def test_a_share_reads_as_written() -> None:
    churn = parse(
        request(
            'churn = Churn(lifetime_mean=5, cycle_share=0.03, long_share="1/20")\n'
            "run_length = 1000\nstructures = []\n"
        )
    ).workload.churn

    assert (str(churn.cycle_share), str(churn.long_share)) == ("3/100", "1/20")


def test_a_shape_function_brings_its_text_with_its_comments_and_no_more() -> None:
    shape = own(
        "def links(i):\n"
        "    if not i:\n"
        "        return []\n"
        "    return [(0, i)]\n"
        "    # The first object holds each.\n"
        "\n"
        "structures = [Structure(Own(links), 10)]\n"
    )

    assert shape.code == (
        "def links(i):\n"
        "    if not i:\n"
        "        return []\n"
        "    return [(0, i)]\n"
        "    # The first object holds each.\n"
    )


def test_a_nested_shape_function_brings_its_text_dedented() -> None:
    shape = own(
        "def outer():\n"
        "    def chain(i):\n"
        "        return [(i - 1, i)] if i else []\n"
        "    return chain\n"
        "structures = [Structure(Own(outer()), 10)]\n"
    )

    assert shape.code == "def chain(i):\n    return [(i - 1, i)] if i else []\n"


def test_a_shape_can_be_code_as_text() -> None:
    shape = own('structures = [Structure(Own("links = lambda i: [(0, i)]"), 10)]\n')

    assert shape.links(3) == [(0, 3)]


def test_a_shape_function_fails_at_its_line_in_the_source() -> None:
    with pytest.raises(ValueError, match=r"f\(1\) raised NameError at line 5:"):
        own(
            "WIDTH = 2\n"
            "def f(i):\n"
            "    return [(0, i)] * WIDTH if i else []\n"
            "structures = [Structure(Own(f), 10)]\n"
        )


def test_a_request_reads_its_source_once() -> None:
    # The worker reads a request four times, and each reading gets one workload,
    # whatever the source draws.
    text = request(
        "import random\n"
        + CHURN
        + "structures = [Structure(Tree(), random.randint(1, 10**9))]\n"
    )

    assert parse(text) is parse(text)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("x = (", r"line 3 of your workload: '\(' was never closed"),
        ("", "your workload sets no structures"),
        ("structures = 5", r"your workload sets structures to 5, not a list"),
        ("structures = [1]", r"structures holds 1, not a Structure\(...\)"),
        ("structures = []\nrun_length = True", "sets run_length to True"),
        ("structures = []\nrun_length = 0", "a run_length of 0 kB allocates nothing"),
        ("structures = []\nseed = '1'", "sets seed to '1', not a whole number"),
        (
            "structures = []\nsettings = Settings(threshold1=0)",
            "a threshold1 of 0 leaves the incremental collector no aging space",
        ),
        (
            "structures = [Structure('tree', 10)]",
            "line 3 of your workload: 'tree' is no shape",
        ),
        (
            "structures = [Structure(Tree(), 0)]",
            "line 3 of your workload: a structure of 0 objects builds nothing",
        ),
        ("structures = [Structure(Tree(), 10, root='sys')]", "no root 'sys'"),
        (
            "structures = [Structure(Tree(), '10')]",
            "your workload raised TypeError at line 3:",
        ),
        (
            "structures = [Structure(Own(lambda i: []), 10)]",
            "Own takes a function your workload defines with def, or code as text",
        ),
        (
            "import functools\n"
            "@functools.cache\n"
            "def f(i):\n"
            "    return []\n"
            "structures = [Structure(Own(f), 10)]",
            "Own takes a function",
        ),
        (
            "def f(i):\n"
            "    return [(0, i), (i, i + 1)] if i else []\n"
            "structures = [Structure(Own(f), 10)]",
            r"f\(1\) gives \(1, 2\): a link joins two of objects 0 to 1",
        ),
    ],
)
def test_a_source_the_simulator_cannot_run_names_what_it_cannot(
    source: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse(request(CHURN + source))


def test_a_request_with_a_source_holds_no_other_workload() -> None:
    with pytest.raises(ValueError, match="request has no field 'run_length'"):
        parse(json.dumps({"source": "", "every": 5, "run_length": 1}))
