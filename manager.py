from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_CONFIG = {
    "catalog": "Y2F0YWxvZy5qc29u",
    "library": "Z2FtZWh1Yl9jYXRhbG9nLmpzb24=",
    "downloads": "ZG93bmxvYWRz",
    "installs": "aW5zdGFsbGVk",
    "user_agent": "R2FtZUh1Yk1hbmFnZXIvMC4xIChsYXdmdWwtZGlyZWN0LXVybHMtb25seSk=",
}

_BLOCKED_DOMAINS = {
    "shrinkme.click",
    "mrproblogger.com",
    "filecrypt.cc",
    "www.filecrypt.cc",
}
_CHUNK_SIZE = 1024 * 256
_MAX_WORKERS = 6


class UnsafePipelineError(RuntimeError):
    """Raised when a source requires bypassing shorteners, captchas, or access controls."""


@dataclass(slots=True)
class ContentItem:
    title: str
    urls: list[str]
    source: str = ""
    description: str = ""
    password: str = ""
    tags: list[str] = field(default_factory=list)
    checksum: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ContentItem":
        title = str(data.get("title") or data.get("t") or "").strip()
        urls = data.get("urls") or data.get("downloads") or data.get("d") or []
        if isinstance(urls, str):
            urls = [urls]
        clean_urls = [str(url).strip() for url in urls if str(url).strip()]
        if not title:
            raise ValueError("Catalog entries must include a title.")
        if not clean_urls:
            raise ValueError(f"Catalog entry {title!r} must include at least one direct URL.")
        return cls(
            title=title,
            urls=clean_urls,
            source=str(data.get("source") or data.get("u") or ""),
            description=str(data.get("description") or ""),
            password=str(data.get("password") or data.get("p") or ""),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
            checksum=str(data.get("checksum") or ""),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "urls": self.urls,
            "source": self.source,
            "description": self.description,
            "password": self.password,
            "tags": self.tags,
            "checksum": self.checksum,
        }

    @property
    def safe_name(self) -> str:
        name = re.sub(r"[^A-Za-z0-9._ -]", "_", self.title).strip()
        return name or hashlib.sha1(self.title.encode("utf-8")).hexdigest()[:12]


class _X:
    """Thread-safe catalog acquisition for lawful JSON catalog sources."""

    def __init__(self, source: str | None = None, workers: int = _MAX_WORKERS) -> None:
        self.source = source or _decode("catalog")
        self.workers = max(1, workers)
        self.catalog: list[ContentItem] = []
        self._lock = threading.Lock()
        self._headers = {"User-Agent": _decode("user_agent")}

    def _read(self, source: str) -> str:
        parsed = urllib.parse.urlparse(source)
        if parsed.scheme in {"http", "https"}:
            request = urllib.request.Request(source, headers=self._headers)
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=30) as response:
                        content_type = response.headers.get("Content-Type", "")
                        if "json" not in content_type.lower() and not parsed.path.lower().endswith(".json"):
                            raise ValueError("Remote catalog sources must serve JSON content.")
                        return response.read(1024 * 1024 * 4).decode("utf-8")
                except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
                    last_error = exc
                    time.sleep(1 + attempt)
            raise RuntimeError(f"Could not read remote catalog {source!r}: {last_error}")
        if parsed.scheme:
            raise ValueError("Catalog source must be a local path or HTTP(S) JSON URL.")
        return Path(source).expanduser().read_text(encoding="utf-8")

    def _page_source(self, page: int) -> str:
        if "{page}" in self.source:
            return self.source.format(page=page)
        if page == 1:
            return self.source
        return ""

    def _parse_payload(self, payload: str, source: str) -> list[ContentItem]:
        decoded = json.loads(payload)
        raw_items = decoded.get("games", decoded.get("items", decoded)) if isinstance(decoded, dict) else decoded
        if not isinstance(raw_items, list):
            raise ValueError(f"Catalog page {source!r} must be a JSON list or object with games/items.")
        items = [ContentItem.from_mapping(item) for item in raw_items]
        for item in items:
            self._validate_direct_urls(item.urls)
        return items

    def _fetch_page(self, page: int) -> list[ContentItem]:
        source = self._page_source(page)
        if not source:
            return []
        payload = self._read(source)
        return self._parse_payload(payload, source)

    def _validate_direct_urls(self, urls: list[str]) -> None:
        for url in urls:
            parsed = urllib.parse.urlparse(url)
            hostname = (parsed.hostname or "").lower()
            if parsed.scheme not in {"http", "https"}:
                raise ValueError(f"Only HTTP(S) direct URLs are supported: {url}")
            if hostname in _BLOCKED_DOMAINS:
                raise UnsafePipelineError(f"Bypass/captcha sources are not supported: {hostname}")

    def scrape_mt(self, max_pages: int | None = None) -> list[ContentItem]:
        pages = range(1, (max_pages or 1) + 1)
        results: list[ContentItem] = []
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._fetch_page, page): page for page in pages}
            for future in as_completed(futures):
                page_items = future.result()
                with self._lock:
                    self.catalog.extend(page_items)
                    results.extend(page_items)
        results.sort(key=lambda item: item.title.lower())
        with self._lock:
            self.catalog = results[:]
        return results

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path or _decode("library"))
        payload = {"games": [item.to_mapping() for item in self.catalog]}
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target


class _DM:
    """Download manager for authorized direct links and multipart archive sets."""

    def __init__(self, output_dir: str | Path | None = None, workers: int = _MAX_WORKERS) -> None:
        self.output_dir = Path(output_dir or _decode("downloads"))
        self.workers = max(1, workers)
        self._headers = {"User-Agent": _decode("user_agent")}
        self._lock = threading.Lock()
        self._progress_lock = threading.Lock()

    def _filename(self, url: str, index: int) -> str:
        path_name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
        if not path_name:
            path_name = f"part_{index:03d}.bin"
        return re.sub(r"[^A-Za-z0-9._ -]", "_", path_name)

    def _remote_size(self, url: str) -> int | None:
        request = urllib.request.Request(url, headers=self._headers, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                size = response.headers.get("Content-Length")
                return int(size) if size else None
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, ValueError):
            return None

    def download_part(self, url: str, destination: Path, callback: Callable[[Path, int, int | None], None] | None = None) -> Path:
        parsed = urllib.parse.urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname in _BLOCKED_DOMAINS:
            raise UnsafePipelineError(f"Bypass/captcha sources are not supported: {hostname}")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Only HTTP(S) URLs are supported: {url}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        total = self._remote_size(url)
        existing = destination.stat().st_size if destination.exists() else 0
        if total is not None and existing >= total:
            return destination

        headers = dict(self._headers)
        mode = "wb"
        if existing and total:
            headers["Range"] = f"bytes={existing}-"
            mode = "ab"

        request = urllib.request.Request(url, headers=headers)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    if mode == "ab" and getattr(response, "status", None) != 206:
                        mode = "wb"
                        existing = 0
                    downloaded = existing
                    with destination.open(mode) as handle:
                        while True:
                            chunk = response.read(_CHUNK_SIZE)
                            if not chunk:
                                break
                            handle.write(chunk)
                            downloaded += len(chunk)
                            if callback:
                                callback(destination, downloaded, total)
                return destination
            except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
                last_error = exc
                time.sleep(1 + attempt)
        raise RuntimeError(f"Download failed for {url!r}: {last_error}")

    def download_game(self, item: ContentItem, callback: Callable[[Path, int, int | None], None] | None = None) -> tuple[list[Path], str]:
        game_dir = self.output_dir / item.safe_name
        with ThreadPoolExecutor(max_workers=min(self.workers, len(item.urls))) as executor:
            futures = []
            for index, url in enumerate(item.urls, start=1):
                futures.append(executor.submit(self.download_part, url, game_dir / self._filename(url, index), callback))
            paths = [future.result() for future in as_completed(futures)]
        return sorted(paths, key=lambda path: path.name.lower()), item.password


class _EX:
    """Archive extraction and installer discovery."""

    ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".rar")
    FIRST_PART_PATTERNS = (
        re.compile(r"\.part0*1\.rar$", re.IGNORECASE),
        re.compile(r"\.part0*01\.rar$", re.IGNORECASE),
        re.compile(r"\.r00$", re.IGNORECASE),
    )

    def __init__(self, install_dir: str | Path | None = None) -> None:
        self.install_dir = Path(install_dir or _decode("installs"))

    def first_archive(self, parts: list[Path]) -> Path | None:
        archives = [part for part in parts if self._is_archive(part)]
        if not archives:
            return None
        first_parts = [part for part in archives if any(pattern.search(part.name) for pattern in self.FIRST_PART_PATTERNS)]
        return sorted(first_parts or archives, key=lambda path: path.name.lower())[0]

    def _is_archive(self, path: Path) -> bool:
        return path.name.lower().endswith(self.ARCHIVE_SUFFIXES)

    def extract(self, parts: list[Path], title: str, password: str = "") -> Path:
        archive = self.first_archive(parts)
        if archive is None:
            raise ValueError("No supported archive files were downloaded.")
        destination = self.install_dir / re.sub(r"[^A-Za-z0-9._ -]", "_", title).strip()
        destination.mkdir(parents=True, exist_ok=True)
        lower = archive.name.lower()

        if lower.endswith(".zip"):
            with zipfile.ZipFile(archive) as zip_file:
                zip_file.extractall(destination, pwd=password.encode("utf-8") if password else None)
            return destination

        if lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            with tarfile.open(archive) as tar_file:
                tar_file.extractall(destination, filter="data")
            return destination

        self._extract_rar(archive, destination, password)
        return destination

    def _extract_rar(self, archive: Path, destination: Path, password: str) -> None:
        binary = shutil.which("unrar") or shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
        if binary:
            executable = Path(binary).name.lower()
            command = [binary, "x", "-y"]
            if password:
                command.append(f"-p{password}")
            if executable.startswith("unrar"):
                command.extend([str(archive), str(destination)])
            else:
                command.extend([f"-o{destination}", str(archive)])
            subprocess.run(command, check=True)
            return

        rarfile_spec = importlib.util.find_spec("rarfile")
        if rarfile_spec is None:
            raise RuntimeError("RAR extraction requires unrar/7z or the optional rarfile package.")
        rarfile = importlib.import_module("rarfile")
        with rarfile.RarFile(archive) as rar_archive:
            rar_archive.extractall(destination, pwd=password or None)

    def find_installer(self, content_dir: Path) -> list[Path]:
        preferred = {"setup.exe", "install.exe", "installer.exe", "autorun.exe"}
        installers: list[Path] = []
        for root, _, files in os.walk(content_dir):
            for filename in files:
                lower = filename.lower()
                path = Path(root) / filename
                if lower in preferred or (lower.endswith(".exe") and any(token in lower for token in ("setup", "install"))):
                    installers.append(path)
        return sorted(installers, key=lambda path: str(path).lower())


class ContentManager:
    def __init__(self, catalog_path: str | Path | None = None) -> None:
        self.catalog_path = Path(catalog_path or _decode("library"))
        self._x = _X()
        self._dm = _DM()
        self._ex = _EX()
        self._progress_lock = threading.Lock()

    def update_catalog(self, source: str | None = None, pages: int | None = None, workers: int = _MAX_WORKERS) -> list[ContentItem]:
        self._x = _X(source=source, workers=workers)
        items = self._x.scrape_mt(max_pages=pages)
        self._x.save(self.catalog_path)
        return items

    def load_catalog(self) -> list[ContentItem]:
        if not self.catalog_path.exists():
            return []
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        raw_items = payload.get("games", payload) if isinstance(payload, dict) else payload
        return [ContentItem.from_mapping(item) for item in raw_items]

    def list_games(self, title_filter: str | None = None) -> list[ContentItem]:
        items = self.load_catalog()
        if title_filter:
            needle = title_filter.lower()
            items = [item for item in items if needle in item.title.lower()]
        for index, item in enumerate(items):
            print(f"[{index}] {item.title} ({len(item.urls)} file{'s' if len(item.urls) != 1 else ''})")
        return items

    def download(self, game_index: int | None = None, title_filter: str | None = None, install: bool = True) -> list[Path]:
        items = self.list_games(title_filter=title_filter)
        if game_index is not None:
            if game_index < 0 or game_index >= len(items):
                raise IndexError(f"Catalog index out of range: {game_index}")
            items = [items[game_index]]
        downloaded: list[Path] = []
        for item in items:
            print(f"Downloading {item.title}...")
            parts, password = self._dm.download_game(item, self._progress)
            downloaded.extend(parts)
            if install:
                destination = self._ex.extract(parts, item.title, password)
                installers = self._ex.find_installer(destination)
                if installers:
                    print("Installers found:")
                    for installer in installers:
                        print(f"  {installer}")
        return downloaded

    def _progress(self, path: Path, downloaded: int, total: int | None) -> None:
        with self._progress_lock:
            if total:
                pct = downloaded / max(total, 1) * 100
                print(f"\r{path.name}: {pct:5.1f}%", end="", flush=True)
            else:
                print(f"\r{path.name}: {downloaded} bytes", end="", flush=True)
            if total and downloaded >= total:
                print()


def _decode(key: str) -> str:
    return base64.b64decode(_CONFIG[key]).decode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Digital Content Manager for lawful direct-download catalogs")
    parser.add_argument("action", choices=["update", "download", "list"], help="Action to perform")
    parser.add_argument("--source", "-s", help="Local or HTTP(S) JSON catalog source. Use {page} for paged catalogs.")
    parser.add_argument("--pages", "-p", type=int, help="Number of catalog pages to load when --source contains {page}")
    parser.add_argument("--index", "-i", type=int, help="Catalog index to download")
    parser.add_argument("--filter", "-f", help="Filter titles by substring")
    parser.add_argument("--catalog", default=_decode("library"), help="Catalog storage path")
    parser.add_argument("--no-install", action="store_true", help="Download only; do not extract archives")
    parser.add_argument("--workers", type=int, default=_MAX_WORKERS, help="Maximum worker threads")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = ContentManager(catalog_path=args.catalog)
    if args.action == "update":
        items = manager.update_catalog(source=args.source, pages=args.pages, workers=args.workers)
        print(f"Saved {len(items)} catalog item(s) to {args.catalog}")
    elif args.action == "list":
        manager.list_games(title_filter=args.filter)
    elif args.action == "download":
        manager.download(game_index=args.index, title_filter=args.filter, install=not args.no_install)
    return 0


if __name__ == "__main__":
    sys.exit(main())
