import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from gamehub_manager.catalog import load_catalog
from gamehub_manager.downloader import filename_from_url
from gamehub_manager.installer import first_archive, is_archive
from gamehub_manager.models import GameEntry
from manager import _X, _DM, ContentManager


def test_filename_from_url_sanitizes_names() -> None:
    assert filename_from_url("https://example.com/files/My%20Game%3F.zip") == "My Game_.zip"


def test_archive_detection_supports_multipart_rar() -> None:
    assert is_archive(Path("Game.part1.rar"))
    assert first_archive([Path("Game.part2.rar"), Path("Game.part1.rar")]) == Path("Game.part1.rar")


def test_game_entry_folder_name_is_safe() -> None:
    entry = GameEntry(title="Bad:/Name*", urls=["https://example.com/game.zip"])
    assert entry.safe_folder_name == "Bad__Name_"


def test_load_catalog_from_local_json(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        '{"games": [{"title": "Legal Game", "description": "Demo", "urls": ["https://example.com/legal.zip"]}]}',
        encoding="utf-8",
    )

    items = load_catalog(str(catalog))

    assert len(items) == 1
    assert items[0].title == "Legal Game"
    assert items[0].urls == ["https://example.com/legal.zip"]


def test_x_scrape_mt_returns_catalog_after_scraping() -> None:
    x = _X()
    # _get_listings returning empty stops the loop immediately
    with patch.object(x, '_get_listings', return_value=[]):
        result = x.scrape_mt()
    assert result == []


def test_x_save_writes_json(tmp_path: Path) -> None:
    x = _X()
    x._catalog = [{'t': 'Game One', 'u': 'https://example.com', 'd': [], 'p': 'pw'}]
    out = tmp_path / "catalog.json"
    x.save(str(out))
    data = json.loads(out.read_text())
    assert data[0]['t'] == 'Game One'


def test_dm_get_direct_link_returns_none_on_failure() -> None:
    dm = _DM()
    with patch.object(dm._sess, 'get', side_effect=Exception("network error")):
        result = dm.get_direct_link("https://www.mediafire.com/file/abc")
    assert result is None


def test_content_manager_download_with_no_catalog(tmp_path, capsys) -> None:
    cm = ContentManager()
    # Patch open to simulate missing catalog
    with patch('builtins.open', side_effect=FileNotFoundError):
        cm.download()
    assert "No catalog found" in capsys.readouterr().out
