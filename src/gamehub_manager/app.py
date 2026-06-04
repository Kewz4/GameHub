"""GameHub – dark gaming library manager with Steam cover art."""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as msgbox
import tkinter.filedialog as filedialog
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from gamehub_manager.catalog import load_catalog
from gamehub_manager.downloader import download_many
from gamehub_manager.installer import extract_archive, first_archive
from gamehub_manager.library import LibraryStore
from gamehub_manager.models import GameEntry

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#080810"
SIDEBAR  = "#0b0b1a"
PANEL    = "#0f0f22"
CARD     = "#13132e"
CARD_H   = "#1c1c40"
ACCENT   = "#7c3aed"
ACCENT_H = "#9b59ff"
CYAN     = "#06b6d4"
GREEN    = "#22c55e"
YELLOW   = "#f59e0b"
RED      = "#ef4444"
TEXT     = "#f0f0ff"
SUB      = "#6868a0"
MUTED    = "#30305a"
BORDER   = "#18183a"
INPUT_BG = "#0c0c20"

CARD_HUES = [
    "#7c3aed", "#0891b2", "#059669", "#dc2626",
    "#9333ea", "#d97706", "#2563eb", "#0d9488",
    "#be185d", "#1d4ed8",
]

_STATUS_PALETTE: dict[str, tuple[str, str]] = {
    "queued":      (MUTED,  TEXT),
    "downloading": (CYAN,   "#000"),
    "downloaded":  (YELLOW, "#000"),
    "installing":  (YELLOW, "#000"),
    "installed":   (GREEN,  "#000"),
    "failed":      (RED,    TEXT),
}


def _status_color(status: str) -> tuple[str, str]:
    for key, pair in _STATUS_PALETTE.items():
        if status.startswith(key):
            return pair
    return RED, TEXT


def _darken(hex_color: str, amount: int = 30) -> str:
    r = max(0, int(hex_color[1:3], 16) - amount)
    g = max(0, int(hex_color[3:5], 16) - amount)
    b = max(0, int(hex_color[5:7], 16) - amount)
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Cover art fetcher (Steam API) ─────────────────────────────────────────────

class CoverFetcher:
    """Background fetcher for Steam cover images and descriptions."""

    COVER_W, COVER_H = 230, 115
    _UA = {"User-Agent": "GameHub/0.1"}

    def __init__(self, cache_dir: Path):
        self._cache = cache_dir
        self._cache.mkdir(parents=True, exist_ok=True)
        self._pending: set[str] = set()

    def fetch(self, game: GameEntry,
              callback: Callable[[str, object | None, str], None]) -> None:
        """Start async fetch; calls callback(game_id, PhotoImage|None, desc)."""
        if game.game_id in self._pending:
            return
        self._pending.add(game.game_id)
        threading.Thread(
            target=self._worker, args=(game, callback), daemon=True
        ).start()

    def _worker(self, game: GameEntry,
                callback: Callable[[str, object | None, str], None]) -> None:
        img_path = self._cache / f"{game.game_id}.jpg"
        desc_path = self._cache / f"{game.game_id}.txt"
        try:
            desc = desc_path.read_text(encoding="utf-8") if desc_path.exists() else ""
            if not img_path.exists():
                img_url, desc = self._search_steam(game.title)
                if img_url:
                    data = self._get(img_url)
                    if data:
                        img_path.write_bytes(data)
                if desc:
                    desc_path.write_text(desc, encoding="utf-8")

            photo = None
            if img_path.exists() and HAS_PIL:
                img = Image.open(img_path).resize(
                    (self.COVER_W, self.COVER_H), Image.LANCZOS
                )
                photo = ImageTk.PhotoImage(img)

            callback(game.game_id, photo, desc)
        except Exception:
            callback(game.game_id, None, "")

    def _search_steam(self, title: str) -> tuple[str, str]:
        q = urllib.parse.quote(title)
        data = self._get_json(
            f"https://store.steampowered.com/api/storesearch/?term={q}&l=en&cc=US"
        )
        items = (data or {}).get("items", [])
        if not items:
            return "", ""
        app_id = items[0]["id"]
        img_url = (
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
        )
        detail = self._get_json(
            f"https://store.steampowered.com/api/appdetails"
            f"?appids={app_id}&fields=short_description"
        )
        desc = (
            (detail or {})
            .get(str(app_id), {})
            .get("data", {})
            .get("short_description", "")
        )
        return img_url, desc

    def _get_json(self, url: str) -> dict | None:
        try:
            req = urllib.request.Request(url, headers=self._UA)
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read().decode())
        except Exception:
            return None

    def _get(self, url: str) -> bytes | None:
        try:
            req = urllib.request.Request(url, headers=self._UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read()
        except Exception:
            return None


# ── Reusable widgets ──────────────────────────────────────────────────────────

class _Btn(tk.Label):
    """Flat pill-shaped button."""
    def __init__(self, parent, text: str, command: Callable,
                 color: str = ACCENT, fg: str = TEXT, font_size: int = 9, **kw):
        super().__init__(parent, text=text, fg=fg, bg=color,
                         font=("Helvetica", font_size, "bold"),
                         cursor="hand2", padx=10, pady=4, **kw)
        hover = _darken(color, 25)
        self.bind("<Enter>",    lambda _: self.config(bg=hover))
        self.bind("<Leave>",    lambda _: self.config(bg=color))
        self.bind("<Button-1>", lambda _: command())


class _Input(tk.Entry):
    """Dark-styled entry field."""
    def __init__(self, parent, textvariable=None, show="", **kw):
        super().__init__(parent, textvariable=textvariable, show=show,
                         bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=("Helvetica", 10),
                         highlightthickness=1, highlightcolor=ACCENT,
                         highlightbackground=BORDER, **kw)


class _ScrollFrame(tk.Frame):
    """Vertically scrollable frame."""
    def __init__(self, parent, bg=BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._sb.set)
        self._sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda _: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"))


class _SideNavItem(tk.Frame):
    """One row in the sidebar navigation."""
    def __init__(self, parent, icon: str, label: str, command: Callable, **kw):
        super().__init__(parent, bg=SIDEBAR, cursor="hand2", **kw)
        self._cmd = command
        self._active = False
        self._icon = tk.Label(self, text=icon, bg=SIDEBAR, fg=SUB,
                              font=("Helvetica", 16), padx=16, pady=12)
        self._text = tk.Label(self, text=label, bg=SIDEBAR, fg=SUB,
                              font=("Helvetica", 10), anchor="w")
        self._icon.pack(side="left")
        self._text.pack(side="left", fill="x", expand=True)
        for w in (self, self._icon, self._text):
            w.bind("<Enter>",    self._hover_on)
            w.bind("<Leave>",    self._hover_off)
            w.bind("<Button-1>", lambda _: self._cmd())

    def _hover_on(self, _=None):
        if not self._active:
            for w in (self, self._icon, self._text):
                w.config(bg=CARD)

    def _hover_off(self, _=None):
        if not self._active:
            for w in (self, self._icon, self._text):
                w.config(bg=SIDEBAR)

    def set_active(self, state: bool):
        self._active = state
        bg = CARD   if state else SIDEBAR
        fg = TEXT   if state else SUB
        ic = ACCENT if state else SUB
        for w in (self, self._icon, self._text):
            w.config(bg=bg)
        self._icon.config(fg=ic)
        self._text.config(fg=fg)


# ── Game card ─────────────────────────────────────────────────────────────────

class GameCard(tk.Frame):
    W, H = 230, 280

    def __init__(self, parent, game: GameEntry, on_action: Callable,
                 photo=None, desc: str = "", **kw):
        super().__init__(parent, bg=CARD, width=self.W, height=self.H,
                         relief="flat", bd=0, cursor="hand2", **kw)
        self.propagate(False)
        self.game    = game
        self._action = on_action
        self._accent = CARD_HUES[hash(game.title) % len(CARD_HUES)]
        self._photo  = photo   # kept alive here to prevent GC
        self._desc   = desc
        self._build()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()

        # ── Cover / banner ────────────────────────────────────────────────────
        cover_h = CoverFetcher.COVER_H
        if self._photo and HAS_PIL:
            cover = tk.Label(self, image=self._photo, bg=CARD,
                             width=self.W, height=cover_h)
            cover.image = self._photo  # extra ref
            cover.pack(fill="x")
        else:
            # Colour gradient placeholder
            banner = tk.Canvas(self, bg=self._accent, width=self.W,
                               height=cover_h, highlightthickness=0)
            banner.pack(fill="x")
            banner.create_text(
                self.W // 2, cover_h // 2,
                text=self.game.title[:18],
                fill="#ffffff33", font=("Helvetica", 18, "bold"),
            )

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=CARD, padx=10, pady=8)
        body.pack(fill="both", expand=True)

        # Title
        title = self.game.title
        display = (title[:24] + "…") if len(title) > 25 else title
        tk.Label(body, text=display, bg=CARD, fg=TEXT,
                 font=("Helvetica", 10, "bold"),
                 anchor="w", justify="left").pack(fill="x")

        # Description (2 lines)
        if self._desc:
            short = self._desc[:80] + ("…" if len(self._desc) > 80 else "")
            tk.Label(body, text=short, bg=CARD, fg=SUB,
                     font=("Helvetica", 8), anchor="w",
                     wraplength=210, justify="left").pack(fill="x", pady=(2, 0))

        # Status badge
        bg_s, fg_s = _status_color(self.game.status)
        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x", pady=(5, 4))
        tk.Label(row, text=f"  {self.game.status}  ",
                 bg=bg_s, fg=fg_s,
                 font=("Helvetica", 7, "bold"),
                 padx=2, pady=2).pack(side="left")
        if self.game.download_paths:
            tk.Label(row, text=f"  {len(self.game.download_paths)} file(s)",
                     bg=CARD, fg=MUTED, font=("Helvetica", 7)).pack(side="left", padx=6)

        # Action buttons
        btns = tk.Frame(body, bg=CARD)
        btns.pack(fill="x")

        st = self.game.status
        if st == "queued" or st.startswith("download failed"):
            _Btn(btns, "⬇  Download",
                 lambda g=self.game: self._action("download", g),
                 color=ACCENT, font_size=8).pack(side="left", padx=(0, 4))
        elif st == "downloaded" or st.startswith("install failed"):
            _Btn(btns, "📦  Install",
                 lambda g=self.game: self._action("install", g),
                 color="#059669", font_size=8).pack(side="left", padx=(0, 4))
        elif st == "installed":
            _Btn(btns, "✓  Installed", lambda: None,
                 color="#0d3320", fg=GREEN, font_size=8).pack(side="left", padx=(0, 4))
        elif st in ("downloading", "installing"):
            tk.Label(btns, text="⏳  Working…", bg=CARD, fg=YELLOW,
                     font=("Helvetica", 8)).pack(side="left")

        _Btn(btns, "✕",
             lambda g=self.game: self._action("remove", g),
             color="#2a0d0d", fg="#ff6666", font_size=8).pack(side="right")

        self._bind_hover(self)

    def _bind_hover(self, widget):
        widget.bind("<Enter>", lambda _: self.config(bg=CARD_H))
        widget.bind("<Leave>", lambda _: self.config(bg=CARD))
        for child in widget.winfo_children():
            self._bind_hover(child)

    def set_cover(self, photo, desc: str):
        self._photo = photo
        self._desc  = desc
        self._build()


# ── Views ─────────────────────────────────────────────────────────────────────

class LibraryView(tk.Frame):
    COLS = 4

    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._cards: dict[str, GameCard] = {}
        self._build_header()
        self._scroll = _ScrollFrame(self, bg=BG)
        self._scroll.pack(fill="both", expand=True, padx=20)
        self._grid = self._scroll.inner
        self._empty = tk.Label(
            self._grid,
            text="No games in your library yet.\nHead to Catalog or Add Game to get started.",
            bg=BG, fg=SUB, font=("Helvetica", 13), justify="center",
        )

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(20, 12))
        tk.Label(hdr, text="Library", bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold")).pack(side="left")
        self._count_lbl = tk.Label(hdr, text="", bg=BG, fg=SUB,
                                    font=("Helvetica", 11))
        self._count_lbl.pack(side="left", padx=12)

    def refresh(self, games: list[GameEntry]):
        self._count_lbl.config(text=f"{len(games)} game(s)")
        self._empty.pack_forget()
        current_ids = {g.game_id for g in games}

        # Remove stale
        for gid in list(self._cards):
            if gid not in current_ids:
                self._cards[gid].destroy()
                del self._cards[gid]

        # Add / update
        for game in games:
            if game.game_id in self._cards:
                self._cards[game.game_id].game = game
                self._cards[game.game_id]._build()
            else:
                photo = self.app._cover_images.get(game.game_id)
                desc  = self.app._cover_descs.get(game.game_id, "")
                card  = GameCard(self._grid, game, self.app.on_card_action,
                                 photo=photo, desc=desc)
                self._cards[game.game_id] = card
                # Kick off cover fetch
                self.app.fetcher.fetch(game, self.app._cover_callback)

        self._reflow(games)
        if not games:
            self._empty.pack(pady=80)

    def _reflow(self, games: list[GameEntry]):
        for card in self._cards.values():
            card.grid_forget()
        for i, game in enumerate(games):
            row, col = divmod(i, self.COLS)
            self._cards[game.game_id].grid(
                row=row, column=col, padx=8, pady=8, sticky="nw"
            )

    def update_cover(self, game_id: str, photo, desc: str):
        card = self._cards.get(game_id)
        if card:
            card.set_cover(photo, desc)


class CatalogView(tk.Frame):
    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app    = app
        self._items: list[dict] = []
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(20, 4))
        tk.Label(hdr, text="Catalog", bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold")).pack(side="left")

        tk.Label(self,
                 text="Load a local JSON catalog saved by manager.py, or any HTTPS catalog URL.",
                 bg=BG, fg=SUB, font=("Helvetica", 10), anchor="w").pack(
                     fill="x", padx=20, pady=(0, 12))

        # Built-in catalog shortcut
        builtin_row = tk.Frame(self, bg=BG)
        builtin_row.pack(fill="x", padx=20, pady=(0, 8))
        _Btn(builtin_row, "⚡  Load Built-in Catalog", self._load_builtin,
             color=ACCENT, font_size=10).pack(side="left")
        tk.Label(builtin_row, text="  15 free & open-source games, ready to download",
                 bg=BG, fg=SUB, font=("Helvetica", 9)).pack(side="left", padx=8)

        # Source bar
        bar = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        bar.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(bar, text="Or load a custom catalog", bg=PANEL, fg=SUB,
                 font=("Helvetica", 9)).pack(anchor="w")
        src_row = tk.Frame(bar, bg=PANEL)
        src_row.pack(fill="x", pady=(4, 0))
        self._src_var = tk.StringVar()
        _Input(src_row, textvariable=self._src_var).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        _Btn(src_row, "Browse", self._browse, color=MUTED).pack(side="left", padx=(0, 8))
        _Btn(src_row, "Load",   self._load,   color=MUTED).pack(side="left")

        self._count = tk.Label(self, text="", bg=BG, fg=SUB, font=("Helvetica", 10))
        self._count.pack(anchor="w", padx=20, pady=(0, 8))

        self._scroll = _ScrollFrame(self, bg=BG)
        self._scroll.pack(fill="both", expand=True, padx=20)
        self._rows_frame = self._scroll.inner

        # Auto-load built-in catalog on startup
        self.after(100, self._load_builtin)

    def _load_builtin(self):
        try:
            from manager import get_builtin_catalog
            raw = get_builtin_catalog()
        except Exception as exc:
            msgbox.showerror("GameHub", f"Could not load built-in catalog:\n{exc}")
            return
        self._items = [
            {
                "title":       g["title"],
                "urls":        g.get("urls", []),
                "description": g.get("description", ""),
                "password":    g.get("password", ""),
            }
            for g in raw
        ]
        self._render_items()
        self.app.post_log(f"Built-in catalog loaded — {len(self._items)} title(s).")

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Open catalog JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._src_var.set(path)

    def _load(self):
        source = self._src_var.get().strip()
        if not source:
            msgbox.showerror("GameHub", "Enter a catalog source first.")
            return
        try:
            raw = Path(source)
            if raw.exists():
                with raw.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                games_raw = (
                    data.get("games", data) if isinstance(data, dict) else data
                )
                self._items = [
                    {
                        "title":       g.get("title") or g.get("t", "Unknown"),
                        "urls":        g.get("urls")  or g.get("d") or [],
                        "description": g.get("description", ""),
                        "password":    g.get("password") or g.get("p", ""),
                    }
                    for g in games_raw if isinstance(g, dict)
                ]
            else:
                catalog_items = load_catalog(source)
                self._items = [
                    {"title": c.title, "urls": c.urls,
                     "description": c.description, "password": c.password}
                    for c in catalog_items
                ]
        except Exception as exc:
            msgbox.showerror("GameHub", f"Could not load catalog:\n{exc}")
            return

        self._render_items()
        self.app.post_log(f"Catalog loaded — {len(self._items)} title(s).")

    def _render_items(self):
        for w in self._rows_frame.winfo_children():
            w.destroy()
        self._count.config(text=f"{len(self._items)} title(s)")
        if not self._items:
            tk.Label(self._rows_frame, text="No items found.",
                     bg=BG, fg=SUB, font=("Helvetica", 11)).pack(pady=40)
            return
        for i, item in enumerate(self._items):
            bg = CARD if i % 2 == 0 else PANEL
            row = tk.Frame(self._rows_frame, bg=bg, padx=16, pady=10)
            row.pack(fill="x", pady=1)
            info = tk.Frame(row, bg=bg)
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=item["title"], bg=bg, fg=TEXT,
                     font=("Helvetica", 11, "bold"), anchor="w").pack(fill="x")
            if item.get("description"):
                tk.Label(info, text=item["description"][:90], bg=bg, fg=SUB,
                         font=("Helvetica", 9), anchor="w").pack(fill="x")
            tk.Label(info, text=f"{len(item['urls'])} URL(s)",
                     bg=bg, fg=MUTED, font=("Helvetica", 8)).pack(anchor="w")
            _Btn(row, "+ Add to Library",
                 lambda it=item: self.app.add_from_catalog(it),
                 color=ACCENT).pack(side="right", padx=(8, 0))


class AddGameView(tk.Frame):
    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._build()

    def _build(self):
        tk.Frame(self, bg=BG).pack(pady=(20, 0))
        tk.Label(self, text="Add Game", bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold")).pack(anchor="w", padx=20)

        form = tk.Frame(self, bg=PANEL, padx=24, pady=20)
        form.pack(fill="x", padx=20, pady=12)

        def field(label_text, var=None, text_widget=False, show=""):
            tk.Label(form, text=label_text, bg=PANEL, fg=SUB,
                     font=("Helvetica", 9)).pack(anchor="w", pady=(10, 2))
            if text_widget:
                t = tk.Text(form, height=5, bg=INPUT_BG, fg=TEXT,
                            insertbackground=TEXT, relief="flat",
                            font=("Helvetica", 10),
                            highlightthickness=1, highlightcolor=ACCENT,
                            highlightbackground=BORDER)
                t.pack(fill="x")
                return t
            e = _Input(form, textvariable=var, show=show)
            e.pack(fill="x")
            return e

        self._title_var = tk.StringVar()
        self._pw_var    = tk.StringVar()
        field("Game Title", self._title_var)
        self._urls_box = field("Direct Download URLs  (one per line)", text_widget=True)
        field("Archive Password (optional)", self._pw_var, show="*")

        tk.Frame(form, bg=PANEL, height=16).pack()
        _Btn(form, "Add to Library", self._submit,
             color=ACCENT, font_size=10).pack(anchor="e")

    def _submit(self):
        title = self._title_var.get().strip()
        urls  = [l.strip() for l in self._urls_box.get("1.0", "end").splitlines()
                 if l.strip()]
        if not title or not urls:
            msgbox.showerror("GameHub", "Title and at least one URL are required.")
            return
        self.app.add_game(title, urls, self._pw_var.get())
        self._title_var.set("")
        self._pw_var.set("")
        self._urls_box.delete("1.0", "end")
        self.app.post_log(f'Added "{title}" to library.')
        self.app.switch_view("library")


class DownloadsView(tk.Frame):
    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, bg=BG, **kw)
        self.app = app
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(20, 12))
        tk.Label(hdr, text="Activity Log", bg=BG, fg=TEXT,
                 font=("Helvetica", 20, "bold")).pack(side="left")
        _Btn(hdr, "Clear", self._clear, color=MUTED, font_size=9).pack(side="right")

        self._log = tk.Text(
            self, bg=PANEL, fg=TEXT, font=("Courier", 9),
            relief="flat", state="disabled", wrap="word",
            highlightthickness=0, padx=16, pady=12,
        )
        self._log.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self._log.tag_config("ok",    foreground=GREEN)
        self._log.tag_config("warn",  foreground=YELLOW)
        self._log.tag_config("error", foreground=RED)
        self._log.tag_config("info",  foreground=TEXT)

    def append(self, msg: str):
        self._log.configure(state="normal")
        low = msg.lower()
        tag = (
            "error" if ("fail" in low or "error" in low) else
            "warn"  if "%" in msg else
            "ok"    if ("✓" in msg or "download" in low or "install" in low) else
            "info"
        )
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


# ── Toast ─────────────────────────────────────────────────────────────────────

class _Toast(tk.Toplevel):
    def __init__(self, parent, message: str):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg=ACCENT)
        tk.Label(self, text=message, bg=ACCENT, fg=TEXT,
                 font=("Helvetica", 10), padx=20, pady=10).pack()
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width()  - self.winfo_width()  - 20
        py = parent.winfo_rooty() + parent.winfo_height() - self.winfo_height() - 40
        self.geometry(f"+{px}+{py}")
        self.after(2800, self.destroy)


# ── Main application ──────────────────────────────────────────────────────────

class GameHubApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("GameHub")
        self.geometry("1280x800")
        self.minsize(960, 640)
        self.configure(bg=BG)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                         background=MUTED, troughcolor=PANEL,
                         bordercolor=PANEL, arrowcolor=SUB)

        self.store  = LibraryStore()
        self.games  = self.store.load()
        self._queue: queue.Queue[str] = queue.Queue()

        # Cover art state
        self.fetcher: CoverFetcher = CoverFetcher(self.store.root / "covers")
        self._cover_images: dict[str, object] = {}   # game_id → PhotoImage (keeps ref)
        self._cover_descs:  dict[str, str]    = {}   # game_id → description

        self._nav_items: dict[str, _SideNavItem] = {}
        self._views:     dict[str, tk.Frame]     = {}
        self._active_view = "library"

        self._build()
        self._refresh_library()
        self.after(250, self._drain)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        pane = tk.Frame(self, bg=BG)
        pane.pack(fill="both", expand=True)

        self._make_sidebar(pane).pack(side="left", fill="y")

        content = tk.Frame(pane, bg=BG)
        content.pack(side="left", fill="both", expand=True)

        self._statusbar = tk.Label(
            self, text="Ready", bg=SIDEBAR, fg=SUB,
            font=("Helvetica", 9), anchor="w", padx=16, pady=5,
        )
        self._statusbar.pack(fill="x", side="bottom")

        views_cfg = [
            ("library",   LibraryView),
            ("catalog",   CatalogView),
            ("add",       AddGameView),
            ("downloads", DownloadsView),
        ]
        for name, cls in views_cfg:
            view = cls(content, self)
            view.place(relwidth=1, relheight=1)
            self._views[name] = view

        self.switch_view("library")

    def _make_sidebar(self, parent) -> tk.Frame:
        sb = tk.Frame(parent, bg=SIDEBAR, width=215)
        sb.pack_propagate(False)

        logo = tk.Frame(sb, bg=SIDEBAR, pady=22)
        logo.pack(fill="x")
        tk.Label(logo, text="🎮", bg=SIDEBAR, fg=ACCENT,
                 font=("Helvetica", 30)).pack()
        tk.Label(logo, text="GameHub", bg=SIDEBAR, fg=TEXT,
                 font=("Helvetica", 15, "bold")).pack()
        tk.Label(logo, text="Game Library Manager", bg=SIDEBAR, fg=SUB,
                 font=("Helvetica", 8)).pack()

        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", padx=16, pady=8)

        for key, icon, label in [
            ("library",   "🎮", "Library"),
            ("catalog",   "📦", "Catalog"),
            ("add",       "➕", "Add Game"),
            ("downloads", "📋", "Activity"),
        ]:
            item = _SideNavItem(sb, icon, label, lambda k=key: self.switch_view(k))
            item.pack(fill="x")
            self._nav_items[key] = item

        tk.Frame(sb, bg=SIDEBAR).pack(fill="both", expand=True)
        tk.Label(sb, text="v0.1.0", bg=SIDEBAR, fg=MUTED,
                 font=("Helvetica", 8)).pack(pady=12)
        return sb

    def switch_view(self, name: str):
        for key, item in self._nav_items.items():
            item.set_active(key == name)
        for key, view in self._views.items():
            (view.lift if key == name else view.lower)()
        self._active_view = name

    # ── Cover callback (called from background thread) ─────────────────────────

    def _cover_callback(self, game_id: str, photo, desc: str):
        # Must schedule back onto main thread
        self.after(0, self._apply_cover, game_id, photo, desc)

    def _apply_cover(self, game_id: str, photo, desc: str):
        if photo:
            self._cover_images[game_id] = photo
        if desc:
            self._cover_descs[game_id] = desc
        self._views["library"].update_cover(game_id, photo, desc)

    # ── Game operations ───────────────────────────────────────────────────────

    def add_game(self, title: str, urls: list[str], password: str = ""):
        entry = GameEntry(title=title, urls=urls, password=password)
        self.games.append(entry)
        self.store.save(self.games)
        self._refresh_library()
        _Toast(self, f'Added "{title}"')

    def add_from_catalog(self, item: dict):
        self.add_game(item["title"], item["urls"], item.get("password", ""))

    def on_card_action(self, action: str, game: GameEntry):
        if action == "download":
            threading.Thread(target=self._download, args=(game,), daemon=True).start()
        elif action == "install":
            threading.Thread(target=self._install,  args=(game,), daemon=True).start()
        elif action == "remove":
            self.games = [g for g in self.games if g.game_id != game.game_id]
            self.store.save(self.games)
            self._refresh_library()

    def _download(self, game: GameEntry):
        try:
            game.status = "downloading"
            self._save_refresh()
            paths = download_many(
                game.urls, game.download_dir(self.store.root), self._queue.put
            )
            game.download_paths = [str(p) for p in paths]
            game.status = "downloaded"
            self._queue.put(f'✓ Downloaded: {game.title}')
        except Exception as exc:
            game.status = f"download failed: {exc}"
            self._queue.put(f'✗ Download failed: {game.title} — {exc}')
        finally:
            self._save_refresh()

    def _install(self, game: GameEntry):
        try:
            paths   = [Path(p) for p in game.download_paths]
            archive = first_archive(paths)
            if archive is None:
                raise RuntimeError("No supported archive found in download folder.")
            game.status = "installing"
            self._save_refresh()
            dest = game.destination_dir(self.store.root)
            extract_archive(archive, dest, game.password)
            game.install_path = str(dest)
            game.status = "installed"
            self._queue.put(f'✓ Installed: {game.title}  →  {dest}')
        except Exception as exc:
            game.status = f"install failed: {exc}"
            self._queue.put(f'✗ Install failed: {game.title} — {exc}')
        finally:
            self._save_refresh()

    def _save_refresh(self):
        self.store.save(self.games)
        self._queue.put("__refresh__")

    def _refresh_library(self):
        self._views["library"].refresh(self.games)

    def post_log(self, msg: str):
        self._queue.put(msg)

    # ── Message pump ──────────────────────────────────────────────────────────

    def _drain(self):
        while True:
            try:
                msg = self._queue.get_nowait()
            except queue.Empty:
                break
            if msg == "__refresh__":
                self._refresh_library()
            else:
                self._views["downloads"].append(msg)
                self._statusbar.config(text=msg[:120])
        self.after(250, self._drain)


def main() -> None:
    GameHubApp().mainloop()


if __name__ == "__main__":
    main()
