from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

RAR_SUFFIXES = (".rar", ".part1.rar", ".r00")


def is_archive(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.endswith((".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"))
        or name.endswith(RAR_SUFFIXES)
    )


def first_archive(paths: list[Path]) -> Path | None:
    archives = [path for path in paths if is_archive(path)]
    if not archives:
        return None
    part1 = [path for path in archives if ".part1.rar" in path.name.lower()]
    return sorted(part1 or archives, key=lambda path: path.name.lower())[0]


def extract_archive(archive: Path, destination: Path, password: str = "") -> None:
    destination.mkdir(parents=True, exist_ok=True)
    lower_name = archive.name.lower()

    if lower_name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zip_file:
            pwd = password.encode("utf-8") if password else None
            zip_file.extractall(destination, pwd=pwd)
        return

    if lower_name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
        with tarfile.open(archive) as tar_file:
            tar_file.extractall(destination, filter="data")
        return

    if lower_name.endswith(RAR_SUFFIXES):
        extractor = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz") or shutil.which("unrar")
        if extractor is None:
            raise RuntimeError("RAR extraction requires 7z/7za/7zz or unrar to be installed and on PATH.")
        if Path(extractor).name.lower().startswith("unrar"):
            command = [extractor, "x", "-y"]
            if password:
                command.append(f"-p{password}")
            command.extend([str(archive), str(destination)])
        else:
            command = [extractor, "x", "-y"]
            if password:
                command.append(f"-p{password}")
            command.extend([f"-o{destination}", str(archive)])
        subprocess.run(command, check=True)
        return

    raise ValueError(f"Unsupported archive type: {archive}")
