"""Assemble the site: copy site/ into _site/ and zip the simulator beside it."""

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def assemble(site: Path, package: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(site, out)
    with zipfile.ZipFile(out / "sim.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            name = path.relative_to(package.parent)
            if path.is_file() and "__pycache__" not in name.parts:
                archive.write(path, name.as_posix())


if __name__ == "__main__":
    assemble(ROOT / "site", ROOT / "src" / "pep848_sim", ROOT / "_site")
