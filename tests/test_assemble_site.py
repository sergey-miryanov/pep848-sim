import subprocess
import zipfile
from pathlib import Path

from assemble_site import assemble, keep, version

COMMIT = "0123456789ab"


def make_tree(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, newline="")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def commit(repo: Path, files: dict[str, str]) -> None:
    """A repository at `repo` whose one commit holds `files`."""
    make_tree(repo, files)
    git(repo, "init", "--quiet")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "--message", "site")


def test_copies_the_pages_to_the_top_and_the_rest_to_the_commits_folder(
    tmp_path: Path,
) -> None:
    make_tree(
        tmp_path / "site",
        {
            "index.html": "<p>guide</p>",
            ".nojekyll": "",
            "theme.css": "body {}",
            "js/worker.js": "//",
        },
    )
    make_tree(tmp_path / "pep848_sim", {"__init__.py": ""})

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site", COMMIT)

    out = tmp_path / "_site"
    assert (out / "index.html").read_text() == "<p>guide</p>"
    assert (out / ".nojekyll").exists()
    assert (out / "v" / COMMIT / "theme.css").read_text() == "body {}"
    assert (out / "v" / COMMIT / "js" / "worker.js").read_text() == "//"
    assert sorted(p.name for p in out.iterdir()) == [".nojekyll", "index.html", "v"]


def test_points_a_pages_links_to_the_files_at_the_commits_folder(
    tmp_path: Path,
) -> None:
    page = "\n".join(
        [
            '<link rel="icon" href="data:,">',
            '<link rel="stylesheet" href="theme.css">',
            '<script src="theme.js"></script>',
            '<script type="module" src="gc-widget.js"></script>',
            '<a href="./">home</a> <a href="playground.html">playground</a>',
            '<a href="https://peps.python.org/pep-0848/">PEP 848</a>',
            '<p>The worker unpacks sim.zip and runs "gc-widget.js".</p>',
            "",
        ]
    )
    make_tree(
        tmp_path / "site",
        {
            "index.html": page,
            "playground.html": "",
            "theme.css": "",
            "theme.js": "",
            "gc-widget.js": "",
        },
    )
    make_tree(tmp_path / "pep848_sim", {"__init__.py": ""})

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site", COMMIT)

    assert (tmp_path / "_site" / "index.html").read_bytes().decode() == "\n".join(
        [
            '<link rel="icon" href="data:,">',
            f'<link rel="stylesheet" href="v/{COMMIT}/theme.css">',
            f'<script src="v/{COMMIT}/theme.js"></script>',
            f'<script type="module" src="v/{COMMIT}/gc-widget.js"></script>',
            '<a href="./">home</a> <a href="playground.html">playground</a>',
            '<a href="https://peps.python.org/pep-0848/">PEP 848</a>',
            '<p>The worker unpacks sim.zip and runs "gc-widget.js".</p>',
            "",
        ]
    )


def test_zips_the_package_under_its_own_name_beside_the_worker(tmp_path: Path) -> None:
    make_tree(tmp_path / "site", {"index.html": "", "worker.js": ""})
    make_tree(
        tmp_path / "pep848_sim",
        {
            "__init__.py": "",
            "collectors/__init__.py": "",
            "collectors/incremental.py": "WORK = 0\n",
        },
    )

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site", COMMIT)

    with zipfile.ZipFile(tmp_path / "_site" / "v" / COMMIT / "sim.zip") as archive:
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

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site", COMMIT)

    with zipfile.ZipFile(tmp_path / "_site" / "v" / COMMIT / "sim.zip") as archive:
        assert archive.namelist() == ["pep848_sim/__init__.py"]


def test_replaces_what_an_earlier_assembly_left(tmp_path: Path) -> None:
    make_tree(tmp_path / "site", {"index.html": ""})
    make_tree(tmp_path / "pep848_sim", {"__init__.py": ""})
    make_tree(
        tmp_path / "_site", {"removed.html": "", "v/fedcba987654/sim.zip": "stale"}
    )

    assemble(tmp_path / "site", tmp_path / "pep848_sim", tmp_path / "_site", COMMIT)

    assert sorted(p.name for p in (tmp_path / "_site").iterdir()) == ["index.html", "v"]
    assert [p.name for p in (tmp_path / "_site" / "v").iterdir()] == [COMMIT]


def test_keeps_the_folder_the_live_site_serves(tmp_path: Path) -> None:
    live = "fedcba987654"
    commit(
        tmp_path / "gh-pages",
        {
            "index.html": f'<script src="v/{live}/gc-widget.js"></script>',
            f"v/{live}/gc-widget.js": "// the live widget",
            f"v/{live}/sim.zip": "zip",
            "v/00000000000a/gc-widget.js": "// an older deploy's",
        },
    )
    make_tree(tmp_path / "site", {"index.html": "", "gc-widget.js": "// this deploy's"})
    make_tree(tmp_path / "pep848_sim", {"__init__.py": ""})
    out = tmp_path / "_site"
    assemble(tmp_path / "site", tmp_path / "pep848_sim", out, COMMIT)

    assert keep("HEAD", out, tmp_path / "gh-pages") == live

    assert (out / "v" / live / "gc-widget.js").read_text() == "// the live widget"
    assert (out / "v" / live / "sim.zip").read_text() == "zip"
    assert (out / "v" / COMMIT / "gc-widget.js").read_text() == "// this deploy's"
    assert sorted(p.name for p in (out / "v").iterdir()) == [COMMIT, live]


def test_keeps_the_folder_this_deploy_assembled_when_the_live_site_serves_it(
    tmp_path: Path,
) -> None:
    commit(
        tmp_path / "gh-pages",
        {
            "index.html": f'<script src="v/{COMMIT}/theme.js"></script>',
            f"v/{COMMIT}/theme.js": "// live",
        },
    )
    make_tree(tmp_path / "site", {"index.html": "", "theme.js": "// assembled"})
    make_tree(tmp_path / "pep848_sim", {"__init__.py": ""})
    out = tmp_path / "_site"
    assemble(tmp_path / "site", tmp_path / "pep848_sim", out, COMMIT)

    assert keep("HEAD", out, tmp_path / "gh-pages") == COMMIT

    assert (out / "v" / COMMIT / "theme.js").read_text() == "// assembled"


def test_keeps_nothing_of_a_live_site_without_a_folder(tmp_path: Path) -> None:
    commit(
        tmp_path / "gh-pages",
        {"index.html": '<script src="gc-widget.js"></script>', "gc-widget.js": ""},
    )
    out = tmp_path / "_site"
    out.mkdir()

    assert keep("HEAD", out, tmp_path / "gh-pages") is None

    assert list(out.iterdir()) == []


def test_keeps_nothing_of_a_live_site_without_a_home_page(tmp_path: Path) -> None:
    commit(tmp_path / "gh-pages", {"README.md": ""})
    out = tmp_path / "_site"
    out.mkdir()

    assert keep("HEAD", out, tmp_path / "gh-pages") is None


def test_names_the_commit_the_site_is_assembled_from(tmp_path: Path) -> None:
    commit(tmp_path / "repo", {"index.html": ""})

    assert (
        version(tmp_path / "repo") == git(tmp_path / "repo", "rev-parse", "HEAD")[:12]
    )
