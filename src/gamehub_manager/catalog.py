from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_CATALOG_BYTES = 1024 * 1024


@dataclass(slots=True)
class CatalogItem:
    """A title advertised by a lawful catalog source."""

    title: str
    urls: list[str]
    description: str = ""
    password: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CatalogItem":
        title = str(data.get("title", "")).strip()
        urls = [str(url).strip() for url in data.get("urls", []) if str(url).strip()]
        if not title:
            raise ValueError("Catalog items must include a title.")
        if not urls:
            raise ValueError(f"Catalog item {title!r} must include at least one direct URL.")
        return cls(
            title=title,
            urls=urls,
            description=str(data.get("description", "")).strip(),
            password=str(data.get("password", "")),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
        )


def _read_source(source: str) -> str:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in _ALLOWED_SCHEMES:
        request = urllib.request.Request(source, headers={"User-Agent": "GameHubManager/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower() and not parsed.path.lower().endswith(".json"):
                raise ValueError("Catalog URLs must point to JSON content.")
            data = response.read(_MAX_CATALOG_BYTES + 1)
        if len(data) > _MAX_CATALOG_BYTES:
            raise ValueError("Catalog is too large; the maximum size is 1 MiB.")
        return data.decode("utf-8")

    if parsed.scheme:
        raise ValueError("Catalog source must be a local JSON file or an HTTP(S) JSON URL.")

    return Path(source).expanduser().read_text(encoding="utf-8")


def load_catalog(source: str) -> list[CatalogItem]:
    """Load a JSON catalog from a local path or HTTP(S) URL."""

    payload = json.loads(_read_source(source))
    raw_items = payload.get("games", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise ValueError("Catalog JSON must be a list or an object with a 'games' list.")
    return [CatalogItem.from_dict(item) for item in raw_items]
