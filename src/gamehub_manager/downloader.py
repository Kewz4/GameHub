from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

ProgressCallback = Callable[[str], None]

_CHUNK_SIZE = 1024 * 256
_MAX_WORKERS = 4


def filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    if not name:
        name = "download.bin"
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)


def _remote_size(url: str) -> int | None:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "GameHubManager/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            return int(length) if length else None
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None


def download_file(url: str, destination_dir: Path, progress: ProgressCallback | None = None) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / filename_from_url(url)
    existing_size = target.stat().st_size if target.exists() else 0
    remote_size = _remote_size(url)

    if remote_size is not None and existing_size >= remote_size:
        if progress:
            progress(f"Already downloaded: {target.name}")
        return target

    headers = {"User-Agent": "GameHubManager/0.1"}
    mode = "wb"
    if existing_size and remote_size:
        headers["Range"] = f"bytes={existing_size}-"
        mode = "ab"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if mode == "ab" and response.status != 206:
                mode = "wb"
                existing_size = 0
            downloaded = existing_size
            with target.open(mode + "") as handle:
                while True:
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        total = remote_size or downloaded
                        progress(f"{target.name}: {downloaded / max(total, 1):.0%}")
    except Exception:
        if target.exists() and target.stat().st_size == 0:
            target.unlink(missing_ok=True)
        raise

    return target


def download_many(urls: list[str], destination_dir: Path, progress: ProgressCallback | None = None) -> list[Path]:
    clean_urls = [url.strip() for url in urls if url.strip()]
    if not clean_urls:
        raise ValueError("At least one direct download URL is required.")

    results: list[Path] = []
    workers = min(_MAX_WORKERS, len(clean_urls))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(download_file, url, destination_dir, progress) for url in clean_urls]
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda path: os.fspath(path).lower())
