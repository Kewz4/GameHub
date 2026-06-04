# GameHub Manager

GameHub Manager is a desktop game library manager and installer for **lawful, user-provided download URLs**. It intentionally does not scrape piracy sites, bypass link shorteners, defeat access controls, or automate downloads from pages that require human verification.

## Features

- Add games with one or more direct download URLs you are authorized to use.
- Load available titles from a lawful JSON catalog file or authorized HTTP(S) JSON URL.
- Download multiple files concurrently with resumable HTTP range requests when supported by the server.
- Track download and install state in a local JSON library.
- Extract `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.txz`, and `.rar`/multipart RAR archives.
- RAR extraction uses an installed `7z`, `7za`, `7zz`, or `unrar` executable.
- Optional archive password support for archives you are authorized to extract.
- GitHub Actions workflow builds a Windows `.exe` with PyInstaller.

## Usage

Run from source:

```bash
python -m gamehub_manager.app
```

The app stores downloads and installs in `~/GameHubLibrary` by default. Use the **Library** tab to:

1. Enter a game title.
2. Paste direct download URLs, one per line.
3. Optionally provide an archive password.
4. Click **Add to Library**.
5. Select the game and click **Download Selected**.
6. Click **Install / Extract Selected** after downloads complete.

Use the **Catalog** tab to load a JSON catalog and add selected titles to the library. Catalogs must be lawful sources that provide direct URLs you are authorized to download; the app does not scrape websites or automate access-control bypasses.

Example catalog:

```json
{
  "games": [
    {
      "title": "Example Public Domain Game",
      "description": "A legally redistributable sample title.",
      "urls": ["https://example.com/game.zip"],
      "password": "",
      "tags": ["sample"]
    }
  ]
}
```

## CLI Content Manager

The repository also includes `manager.py`, a CLI-oriented digital content manager for lawful JSON catalogs and direct download URLs. It preserves the requested `_X`, `_DM`, `_EX`, and `ContentManager` class layout while deliberately rejecting shortener, captcha, and access-control bypass sources.

```bash
python manager.py update --source catalog.json
python manager.py update --source "https://example.com/catalog-page-{page}.json" --pages 10
python manager.py list
python manager.py download --index 0
python manager.py download --filter "demo" --no-install
```

`manager.py` supports threaded catalog loading, JSON catalog storage, resumable chunked downloads, multipart archive sets, ZIP/TAR/RAR extraction, and installer discovery for `setup.exe`, `install.exe`, `installer.exe`, and `autorun.exe`. Catalog entries use the same schema shown above.

## Building an EXE locally

```bash
python -m pip install -r requirements-dev.txt
pyinstaller --noconfirm --onefile --windowed --paths src --name GameHubManager src/gamehub_manager/app.py
pyinstaller --noconfirm --onefile --paths src --name GameHubManagerCLI manager.py
```

The GUI executable will be created at `dist/GameHubManager.exe` on Windows, and the CLI executable will be created at `dist/GameHubManagerCLI.exe`.

## Important limits

GameHub Manager only accepts direct URLs that you have the right to download. Do not use it to access infringing content, bypass link shorteners, defeat captchas, or evade website terms of service.
