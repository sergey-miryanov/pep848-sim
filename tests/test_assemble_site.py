import zipfile
from pathlib import Path

from assemble_site import assemble


def make_tree(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, newline="")


def test_copies_the_site(tmp_path: Path) -> None:
    make_tree(tmp_path / "site", {"index.html": "<p>guide</p>", "js/worker.js": "//"})
    make_tree(tmp_path / "pep848_sim", {"__init__.py": ""})

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site")

    assert (tmp_path / "_site" / "index.html").read_text() == "<p>guide</p>"
    assert (tmp_path / "_site" / "js" / "worker.js").read_text() == "//"


def test_zips_the_package_under_its_own_name(tmp_path: Path) -> None:
    make_tree(tmp_path / "site", {"index.html": ""})
    make_tree(
        tmp_path / "pep848_sim",
        {
            "__init__.py": "",
            "collectors/__init__.py": "",
            "collectors/incremental.py": "WORK = 0\n",
        },
    )

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site")

    with zipfile.ZipFile(tmp_path / "_site" / "sim.zip") as archive:
        assert sorted(archive.namelist()) == [
            "pep848_sim/__init__.py",
            "pep848_sim/collectors/__init__.py",
            "pep848_sim/collectors/incremental.py",
        ]
        assert archive.read("pep848_sim/collectors/incremental.py") == b"WORK = 0\n"


def test_leaves_bytecode_caches_out_of_the_zip(tmp_path: Path) -> None:
    make_tree(tmp_path / "site", {"index.html": ""})
    make_tree(
        tmp_path / "pep848_sim",
        {
            "__init__.py": "",
            "__pycache__/__init__.cpython-314.pyc": "",
            "collectors/__pycache__/heap.cpython-314.pyc": "",
        },
    )

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site")

    with zipfile.ZipFile(tmp_path / "_site" / "sim.zip") as archive:
        assert archive.namelist() == ["pep848_sim/__init__.py"]


def test_replaces_what_an_earlier_assembly_left(tmp_path: Path) -> None:
    make_tree(tmp_path / "site", {"index.html": ""})
    make_tree(tmp_path / "pep848_sim", {"__init__.py": ""})
    make_tree(tmp_path / "_site", {"removed.html": "", "sim.zip": "stale"})

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site")

    assert sorted(p.name for p in (tmp_path / "_site").iterdir()) == [
        "index.html",
        "sim.zip",
    ]
    with zipfile.ZipFile(tmp_path / "_site" / "sim.zip") as archive:
        assert archive.namelist() == ["pep848_sim/__init__.py"]
