from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class GameEntry:
    """A library entry for a downloadable game."""

    title: str
    urls: list[str]
    password: str = ""
    game_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "queued"
    download_paths: list[str] = field(default_factory=list)
    install_path: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameEntry":
        return cls(
            title=str(data.get("title", "Untitled")),
            urls=[str(u) for u in data.get("urls", [])],
            password=str(data.get("password", "")),
            game_id=str(data.get("game_id", uuid4().hex)),
            status=str(data.get("status", "queued")),
            download_paths=[str(p) for p in data.get("download_paths", [])],
            install_path=str(data.get("install_path", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id":        self.game_id,
            "title":          self.title,
            "urls":           self.urls,
            "password":       self.password,
            "status":         self.status,
            "download_paths": self.download_paths,
            "install_path":   self.install_path,
        }

    @property
    def safe_folder_name(self) -> str:
        return (
            "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in self.title).strip()
            or self.game_id
        )

    def download_dir(self, root: Path) -> Path:
        return root / "downloads" / self.safe_folder_name

    def destination_dir(self, root: Path) -> Path:
        return root / "installed" / self.safe_folder_name
