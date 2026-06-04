from __future__ import annotations

import json
from pathlib import Path

from .models import GameEntry


class LibraryStore:
    """Persist the local game library to disk."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.home() / "GameHubLibrary"
        self.root.mkdir(parents=True, exist_ok=True)
        self.library_path = self.root / "library.json"

    def load(self) -> list[GameEntry]:
        if not self.library_path.exists():
            return []
        with self.library_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [GameEntry.from_dict(item) for item in data.get("games", [])]

    def save(self, games: list[GameEntry]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"games": [game.to_dict() for game in games]}
        temp_path = self.library_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        temp_path.replace(self.library_path)
