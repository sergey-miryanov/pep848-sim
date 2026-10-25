"""Assemble the site: copy site/ into _site/ and zip the simulator beside it.

The pages stay at the top of _site/, and every other file goes into a folder
named for the commit, v/<commit>/, which the pages' links name. A page then
loads the scripts, the stylesheet and the simulator it was deployed with, even
from a browser that cached another deploy's (ADR 0019). With --keep REF, the
folder the site at git REF serves comes along too, so a page a browser cached
before this deploy still finds its files.
"""

import argparse
import io
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A link in a page: src="gc-widget.js", href="theme.css".
LINK = re.compile(r'\b(src|href)="([^"]+)"')
# The commit's folder a page's links name.
FOLDER = re.compile(r"\bv/([0-9a-f]+)/")


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    ).stdout


def version(repo: Path) -> str:
    """The commit `repo` stands at, as the first 12 digits of its hash."""
    return git(repo, "rev-parse", "HEAD").decode().strip()[:12]


def assemble(site: Path, package: Path, out: Path, commit: str) -> None:
    if out.exists():
        shutil.rmtree(out)
    folder = out / "v" / commit
    shutil.copytree(site, folder)
    # The pages keep their addresses, and Pages reads .nojekyll at the top.
    for path in sorted(folder.iterdir()):
        if path.suffix == ".html" or path.name == ".nojekyll":
            path.rename(out / path.name)
    with zipfile.ZipFile(folder / "sim.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            name = path.relative_to(package.parent)
            if path.is_file() and "__pycache__" not in name.parts:
                archive.write(path, name.as_posix())
    moved = {
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    }
    for page in out.glob("*.html"):
        text = page.read_bytes().decode("utf-8")
        text = LINK.sub(
            lambda m: f'{m[1]}="v/{commit}/{m[2]}"' if m[2] in moved else m[0], text
        )
        page.write_bytes(text.encode("utf-8"))


def keep(ref: str, out: Path, repo: Path) -> str | None:
    """
    Copy into `out` the commit's folder that the home page at git `ref` names,
    unless `out` holds it already, and return the folder's name. None when the
    site at `ref` has no home page or names no folder.
    """
    try:
        page = git(repo, "show", f"{ref}:index.html").decode("utf-8")
    except subprocess.CalledProcessError:
        return None
    match = FOLDER.search(page)
    if not match:
        return None
    name = match[1]
    if not (out / "v" / name).exists():
        with tarfile.open(
            fileobj=io.BytesIO(git(repo, "archive", ref, f"v/{name}"))
        ) as archive:
            archive.extractall(out, filter="data")
    return name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--keep", metavar="REF", help="also keep the folder the site at git REF serves"
    )
    args = parser.parse_args()
    out = ROOT / "_site"
    assemble(ROOT / "site", ROOT / "src" / "pep848_sim", out, version(ROOT))
    if args.keep:
        kept = keep(args.keep, out, ROOT)
        print(
            f"kept v/{kept}/ from {args.keep}"
            if kept
            else f"{args.keep} serves no folder to keep"
        )
