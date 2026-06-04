from pathlib import Path

from gamehub_manager.catalog import load_catalog
from gamehub_manager.downloader import filename_from_url
from gamehub_manager.installer import first_archive, is_archive
from gamehub_manager.models import GameEntry
from manager import ContentItem, ContentManager, UnsafePipelineError, _X


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


def test_manager_rejects_shortener_catalog_urls(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        '{"games": [{"title": "Blocked", "urls": ["https://shrinkme.click/example"]}]}',
        encoding="utf-8",
    )

    scraper = _X(source=str(catalog))

    try:
        scraper.scrape_mt()
    except UnsafePipelineError:
        pass
    else:
        raise AssertionError("Expected shortener catalog URLs to be rejected")


def test_content_manager_update_and_list_from_local_catalog(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.json"
    stored = tmp_path / "stored.json"
    source.write_text(
        '{"games": [{"title": "Legal CLI Game", "urls": ["https://example.com/game.zip"]}]}',
        encoding="utf-8",
    )

    manager = ContentManager(catalog_path=stored)
    items = manager.update_catalog(source=str(source))
    listed = manager.list_games()

    assert [item.title for item in items] == ["Legal CLI Game"]
    assert [item.title for item in listed] == ["Legal CLI Game"]
    assert "Legal CLI Game" in capsys.readouterr().out


def test_content_item_safe_name() -> None:
    assert ContentItem(title="Bad:/Game*", urls=["https://example.com/game.zip"]).safe_name == "Bad__Game_"
