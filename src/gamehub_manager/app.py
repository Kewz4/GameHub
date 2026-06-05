"""GameHub – modern dark game-library manager (CustomTkinter UI)."""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as msgbox
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from gamehub_manager.builtin_catalog import BUILTIN_CATALOG
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

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG        = "#08080f"
SIDEBAR   = "#0d0d1c"
CARD      = "#111128"
CARD_H    = "#181838"
ACCENT    = "#7c3aed"
ACCENT_H  = "#6d28d9"
GREEN     = "#22c55e"
YELLOW    = "#f59e0b"
RED       = "#ef4444"
CYAN      = "#06b6d4"
TEXT      = "#f0f0ff"
SUB       = "#6060a0"
MUTED     = "#25253d"
BORDER    = "#1a1a30"

CARD_HUES = [
    "#7c3aed","#0891b2","#059669","#dc2626",
    "#9333ea","#d97706","#2563eb","#0d9488",
    "#be185d","#1d4ed8",
]

_STATUS_CLR: dict[str, tuple[str, str]] = {
    "queued":      ("#25253d", "#8888bb"),
    "downloading": ("#0e3a4a", "#06b6d4"),
    "downloaded":  ("#3a2e0e", "#f59e0b"),
    "installing":  ("#3a2e0e", "#f59e0b"),
    "installed":   ("#0e3a1e", "#22c55e"),
    "failed":      ("#3a0e0e", "#ef4444"),
}

def _status_clr(status: str) -> tuple[str, str]:
    for k, v in _STATUS_CLR.items():
        if status.startswith(k):
            return v
    return ("#3a0e0e", "#ef4444")

def _darken(h: str, n: int = 25) -> str:
    r, g, b = int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)
    return f"#{max(0,r-n):02x}{max(0,g-n):02x}{max(0,b-n):02x}"


# ── Cover fetcher ─────────────────────────────────────────────────────────────

class CoverFetcher:
    W, H = 230, 112
    _UA = {"User-Agent": "GameHub/0.1"}

    def __init__(self, cache: Path):
        self._cache = cache
        self._cache.mkdir(parents=True, exist_ok=True)
        self._pending: set[str] = set()

    def fetch(self, game: GameEntry, cb: Callable) -> None:
        if game.game_id in self._pending:
            return
        self._pending.add(game.game_id)
        threading.Thread(target=self._worker, args=(game, cb), daemon=True).start()

    def _worker(self, game: GameEntry, cb: Callable) -> None:
        img_path  = self._cache / f"{game.game_id}.jpg"
        desc_path = self._cache / f"{game.game_id}.txt"
        try:
            desc = desc_path.read_text("utf-8") if desc_path.exists() else ""
            if not img_path.exists():
                img_url, desc = self._search_steam(game.title)
                if img_url:
                    data = self._get(img_url)
                    if data:
                        img_path.write_bytes(data)
                if desc:
                    desc_path.write_text(desc, "utf-8")
            photo = None
            if img_path.exists() and HAS_PIL:
                img = Image.open(img_path).resize((self.W, self.H), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            cb(game.game_id, photo, desc)
        except Exception:
            cb(game.game_id, None, "")

    def _search_steam(self, title: str) -> tuple[str, str]:
        q    = urllib.parse.quote(title)
        data = self._json(f"https://store.steampowered.com/api/storesearch/?term={q}&l=en&cc=US")
        items = (data or {}).get("items", [])
        if not items:
            return "", ""
        app_id = items[0]["id"]
        img    = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
        det    = self._json(f"https://store.steampowered.com/api/appdetails?appids={app_id}&fields=short_description")
        desc   = (det or {}).get(str(app_id), {}).get("data", {}).get("short_description", "")
        return img, desc

    def _json(self, url: str) -> dict | None:
        try:
            req = urllib.request.Request(url, headers=self._UA)
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def _get(self, url: str) -> bytes | None:
        try:
            req = urllib.request.Request(url, headers=self._UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read()
        except Exception:
            return None


# ── Console panel ─────────────────────────────────────────────────────────────

class ConsolePanel(ctk.CTkFrame):
    """Collapsible bottom console with colour-coded, timestamped log output."""

    _TAGS = {
        "ok":    "#22c55e",
        "error": "#ef4444",
        "warn":  "#f59e0b",
        "info":  "#8888bb",
        "scrape":"#06b6d4",
    }

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=SIDEBAR, corner_radius=0, **kw)
        self._collapsed = False

        header = ctk.CTkFrame(self, fg_color=MUTED, corner_radius=0, height=32)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="▶  Console", font=("Courier New", 11, "bold"),
                     text_color=TEXT).pack(side="left", padx=12)
        self._toggle_btn = ctk.CTkButton(
            header, text="▼ Hide", width=70, height=24,
            fg_color=MUTED, hover_color=CARD, text_color=SUB,
            font=("Helvetica", 9), command=self.toggle,
        )
        self._toggle_btn.pack(side="right", padx=8, pady=4)

        ctk.CTkButton(
            header, text="Clear", width=56, height=24,
            fg_color=MUTED, hover_color=CARD, text_color=SUB,
            font=("Helvetica", 9), command=self.clear,
        ).pack(side="right", padx=(0, 4), pady=4)

        self._body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._body.pack(fill="both", expand=True)

        self._text = tk.Text(
            self._body, bg=BG, fg=TEXT, font=("Courier New", 9),
            relief="flat", state="disabled", wrap="word",
            highlightthickness=0, padx=10, pady=8, insertbackground=TEXT,
        )
        sb = ctk.CTkScrollbar(self._body, command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._text.pack(fill="both", expand=True)

        for tag, color in self._TAGS.items():
            self._text.tag_config(tag, foreground=color)

    def log(self, msg: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._text.configure(state="normal")
        self._text.insert("end", f"[{ts}] ", "info")
        self._text.insert("end", msg + "\n", tag)
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def toggle(self):
        if self._collapsed:
            self._body.pack(fill="both", expand=True)
            self._toggle_btn.configure(text="▼ Hide")
        else:
            self._body.pack_forget()
            self._toggle_btn.configure(text="▲ Show")
        self._collapsed = not self._collapsed


# ── Game card ─────────────────────────────────────────────────────────────────

class GameCard(ctk.CTkFrame):
    W, H = 232, 288

    def __init__(self, parent, game: GameEntry, on_action: Callable,
                 photo=None, desc: str = "", **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=12,
                         width=self.W, height=self.H, **kw)
        self.pack_propagate(False)
        self.game    = game
        self._action = on_action
        self._accent = CARD_HUES[hash(game.title) % len(CARD_HUES)]
        self._photo  = photo
        self._desc   = desc
        self._build()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()

        # Cover / banner
        if self._photo and HAS_PIL:
            lbl = ctk.CTkLabel(self, image=self._photo, text="",
                               corner_radius=0)
            lbl.image = self._photo
            lbl.pack(fill="x")
        else:
            banner = tk.Canvas(self, bg=self._accent,
                               width=self.W, height=CoverFetcher.H,
                               highlightthickness=0)
            banner.pack(fill="x")
            banner.create_text(
                self.W // 2, CoverFetcher.H // 2,
                text=self.game.title[:16],
                fill="#ffffff22", font=("Helvetica", 20, "bold"),
            )

        body = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0)
        body.pack(fill="both", expand=True, padx=10, pady=(8, 6))

        # Title
        title = self.game.title
        ctk.CTkLabel(body, text=(title[:24]+"…") if len(title)>25 else title,
                     font=("Helvetica", 11, "bold"), text_color=TEXT,
                     anchor="w", wraplength=200).pack(fill="x")

        # Description
        if self._desc:
            ctk.CTkLabel(body, text=self._desc[:72]+"…" if len(self._desc)>72 else self._desc,
                         font=("Helvetica", 8), text_color=SUB,
                         anchor="w", wraplength=200, justify="left").pack(fill="x", pady=(2,0))

        # Status badge
        bg_s, fg_s = _status_clr(self.game.status)
        badge_row = ctk.CTkFrame(body, fg_color=CARD, corner_radius=0)
        badge_row.pack(fill="x", pady=(5, 6))
        ctk.CTkLabel(badge_row, text=f"  {self.game.status}  ",
                     fg_color=bg_s, text_color=fg_s, corner_radius=6,
                     font=("Helvetica", 8, "bold")).pack(side="left")
        if self.game.download_paths:
            ctk.CTkLabel(badge_row, text=f"  {len(self.game.download_paths)} file(s)",
                         text_color=SUB, font=("Helvetica", 8),
                         fg_color=CARD).pack(side="left", padx=6)

        # Buttons
        btn_row = ctk.CTkFrame(body, fg_color=CARD, corner_radius=0)
        btn_row.pack(fill="x")

        st = self.game.status
        if st == "queued" or st.startswith("download failed"):
            ctk.CTkButton(btn_row, text="⬇  Download",
                          command=lambda g=self.game: self._action("download", g),
                          fg_color=ACCENT, hover_color=ACCENT_H, height=28,
                          font=("Helvetica", 9, "bold"),
                          corner_radius=6).pack(side="left", padx=(0, 4))
        elif st == "downloaded" or st.startswith("install failed"):
            ctk.CTkButton(btn_row, text="📦  Install",
                          command=lambda g=self.game: self._action("install", g),
                          fg_color="#059669", hover_color="#047857", height=28,
                          font=("Helvetica", 9, "bold"),
                          corner_radius=6).pack(side="left", padx=(0, 4))
        elif st == "installed":
            ctk.CTkButton(btn_row, text="✓  Installed", command=lambda: None,
                          fg_color="#0d3320", hover_color="#0d3320",
                          text_color=GREEN, height=28,
                          font=("Helvetica", 9, "bold"),
                          corner_radius=6).pack(side="left", padx=(0, 4))
        elif st in ("downloading", "installing"):
            ctk.CTkLabel(btn_row, text="⏳  Working…",
                         text_color=YELLOW, fg_color=CARD,
                         font=("Helvetica", 9)).pack(side="left")

        ctk.CTkButton(btn_row, text="✕",
                      command=lambda g=self.game: self._action("remove", g),
                      fg_color="#2a0d0d", hover_color="#3d1212",
                      text_color="#ff6666", width=32, height=28,
                      font=("Helvetica", 10, "bold"),
                      corner_radius=6).pack(side="right")

    def set_cover(self, photo, desc: str):
        self._photo = photo
        self._desc  = desc
        self._build()


# ── Library view ──────────────────────────────────────────────────────────────

class LibraryView(ctk.CTkFrame):
    COLS = 4

    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, fg_color=BG, corner_radius=0, **kw)
        self.app    = app
        self._cards: dict[str, GameCard] = {}

        hdr = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        hdr.pack(fill="x", padx=24, pady=(24, 12))
        ctk.CTkLabel(hdr, text="Library", font=("Helvetica", 22, "bold"),
                     text_color=TEXT).pack(side="left")
        self._count = ctk.CTkLabel(hdr, text="", font=("Helvetica", 12),
                                    text_color=SUB)
        self._count.pack(side="left", padx=12)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self._scroll.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        self._empty = ctk.CTkLabel(
            self._scroll,
            text="No games yet.\nGo to Catalog or Add Game to get started.",
            font=("Helvetica", 14), text_color=SUB, justify="center",
        )

    def refresh(self, games: list[GameEntry]):
        self._count.configure(text=f"{len(games)} game(s)")
        self._empty.grid_forget()
        current = {g.game_id for g in games}

        for gid in list(self._cards):
            if gid not in current:
                self._cards[gid].destroy()
                del self._cards[gid]

        for game in games:
            if game.game_id in self._cards:
                self._cards[game.game_id].game = game
                self._cards[game.game_id]._build()
            else:
                photo = self.app._cover_images.get(game.game_id)
                desc  = self.app._cover_descs.get(game.game_id, "")
                card  = GameCard(self._scroll, game, self.app.on_card_action,
                                 photo=photo, desc=desc)
                self._cards[game.game_id] = card
                self.app.fetcher.fetch(game, self.app._cover_cb)

        for i, game in enumerate(games):
            row, col = divmod(i, self.COLS)
            self._cards[game.game_id].grid(row=row, column=col,
                                            padx=8, pady=8, sticky="nw")

        if not games:
            self._empty.grid(row=0, column=0, columnspan=self.COLS, pady=80)

    def update_cover(self, gid: str, photo, desc: str):
        if card := self._cards.get(gid):
            card.set_cover(photo, desc)


# ── Catalog view ──────────────────────────────────────────────────────────────

class CatalogView(ctk.CTkFrame):
    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, fg_color=BG, corner_radius=0, **kw)
        self.app     = app
        self._items: list[dict] = []
        self._scraper = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        hdr.pack(fill="x", padx=24, pady=(24, 8))
        ctk.CTkLabel(hdr, text="Catalog", font=("Helvetica", 22, "bold"),
                     text_color=TEXT).pack(side="left")

        # Action bar
        acts = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        acts.pack(fill="x", padx=24, pady=(0, 12))

        ctk.CTkButton(acts, text="⚡  Built-in (15 games)",
                      command=self._load_builtin,
                      fg_color=ACCENT, hover_color=ACCENT_H, height=34,
                      font=("Helvetica", 10, "bold"), corner_radius=8,
                      ).pack(side="left", padx=(0, 8))

        self._scrape_btn = ctk.CTkButton(
            acts, text="🔍  Scrape Live",
            command=self._start_scrape,
            fg_color="#059669", hover_color="#047857", height=34,
            font=("Helvetica", 10, "bold"), corner_radius=8,
        )
        self._scrape_btn.pack(side="left", padx=(0, 12))

        self._progress = ctk.CTkProgressBar(acts, width=160, height=8,
                                             fg_color=MUTED, progress_color=CYAN,
                                             corner_radius=4)
        self._progress.set(0)

        self._scrape_lbl = ctk.CTkLabel(acts, text="", font=("Helvetica", 9),
                                         text_color=YELLOW)
        self._scrape_lbl.pack(side="left")

        # Custom catalog loader
        custom = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        custom.pack(fill="x", padx=24, pady=(0, 12))
        ctk.CTkLabel(custom, text="Custom catalog (local file or HTTPS URL)",
                     font=("Helvetica", 9), text_color=SUB).pack(anchor="w", padx=14, pady=(10,2))
        row = ctk.CTkFrame(custom, fg_color=CARD, corner_radius=0)
        row.pack(fill="x", padx=14, pady=(0, 10))
        self._src_var = tk.StringVar()
        ctk.CTkEntry(row, textvariable=self._src_var, fg_color=BG,
                     border_color=BORDER, text_color=TEXT,
                     font=("Helvetica", 10), corner_radius=6).pack(
                         side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Browse", width=70, fg_color=MUTED,
                      hover_color=CARD_H, font=("Helvetica", 9),
                      corner_radius=6, command=self._browse).pack(side="left", padx=(0,6))
        ctk.CTkButton(row, text="Load", width=60, fg_color=ACCENT,
                      hover_color=ACCENT_H, font=("Helvetica", 9),
                      corner_radius=6, command=self._load_custom).pack(side="left")

        self._count_lbl = ctk.CTkLabel(self, text="", font=("Helvetica", 10),
                                        text_color=SUB)
        self._count_lbl.pack(anchor="w", padx=24, pady=(0, 6))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self._scroll.pack(fill="both", expand=True, padx=20)

        # Auto-load built-in on first open
        self.after(100, self._load_builtin)

    # ── Scraping ──────────────────────────────────────────────────────────────

    def _start_scrape(self):
        try:
            from manager import _X
        except Exception as exc:
            msgbox.showerror("GameHub", f"Could not import manager.py:\n{exc}")
            return
        self._scraper = _X()
        self._items   = []
        self._scrape_btn.configure(text="⏳  Scraping…", state="disabled")
        self._progress.pack(side="left", padx=(0, 8))
        self._progress.start()
        threading.Thread(target=self._scrape_worker, daemon=True).start()

    def _scrape_worker(self):
        try:
            catalog = self._scraper.scrape_mt(progress_cb=self._on_progress)
            items   = self._fmt(catalog)
            self.after(0, self._scrape_done, items)
        except Exception as exc:
            self.after(0, self._scrape_err, str(exc))

    def _on_progress(self, msg: str):
        self.after(0, self._apply_progress, msg)
        if msg.startswith("[Found]"):
            self.after(0, self._live_refresh)

    def _apply_progress(self, msg: str):
        short = (msg[:68] + "…") if len(msg) > 68 else msg
        self._scrape_lbl.configure(text=short)
        # Pick tag based on prefix
        tag = ("ok"     if "[Found]"   in msg else
               "scrape" if "[Page"     in msg or "[Scraping]" in msg else
               "warn"   if "[Bypass"   in msg else
               "error"  if "[Error]"   in msg else "info")
        self.app.console.log(msg, tag)

    def _live_refresh(self):
        snap = self._scraper._catalog[:]
        self._items = self._fmt(snap)
        self._render()

    def _scrape_done(self, items: list):
        self._items = items
        self._render()
        self._scrape_btn.configure(text="🔍  Scrape Live", state="normal")
        self._progress.stop()
        self._progress.pack_forget()
        self._scrape_lbl.configure(text=f"✓ {len(items)} game(s) found")
        self.app.console.log(f"Scrape complete — {len(items)} game(s) found.", "ok")
        try:
            self._scraper.save()
        except Exception:
            pass

    def _scrape_err(self, msg: str):
        self._scrape_btn.configure(text="🔍  Scrape Live", state="normal")
        self._progress.stop()
        self._progress.pack_forget()
        self._scrape_lbl.configure(text="Error — see console")
        self.app.console.log(f"Scrape error: {msg}", "error")

    @staticmethod
    def _fmt(catalog: list) -> list[dict]:
        return [
            {"title": g.get("t","?"), "urls": g.get("d",[]),
             "description": g.get("u",""), "password": g.get("p","")}
            for g in catalog
        ]

    # ── Built-in / custom catalog ─────────────────────────────────────────────

    def _load_builtin(self):
        self._items = [
            {"title": g["title"], "urls": g.get("urls",[]),
             "description": g.get("description",""), "password": g.get("password","")}
            for g in BUILTIN_CATALOG
        ]
        self._render()
        self.app.console.log(f"Built-in catalog — {len(self._items)} titles.", "ok")

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Open catalog JSON",
            filetypes=[("JSON files","*.json"),("All files","*.*")],
        )
        if path:
            self._src_var.set(path)

    def _load_custom(self):
        source = self._src_var.get().strip()
        if not source:
            msgbox.showerror("GameHub", "Enter a source first.")
            return
        try:
            raw = Path(source)
            if raw.exists():
                data = json.loads(raw.read_text("utf-8"))
                games = data.get("games", data) if isinstance(data, dict) else data
                self._items = [
                    {"title": g.get("title") or g.get("t","?"),
                     "urls":  g.get("urls") or g.get("d",[]),
                     "description": g.get("description",""),
                     "password":    g.get("password") or g.get("p",""),
                    } for g in games if isinstance(g, dict)
                ]
            else:
                items = load_catalog(source)
                self._items = [
                    {"title": c.title, "urls": c.urls,
                     "description": c.description, "password": c.password}
                    for c in items
                ]
        except Exception as exc:
            msgbox.showerror("GameHub", f"Could not load catalog:\n{exc}")
            return
        self._render()
        self.app.console.log(f"Loaded catalog: {len(self._items)} titles.", "ok")

    def _render(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._count_lbl.configure(text=f"{len(self._items)} title(s)")
        for i, item in enumerate(self._items):
            bg = CARD if i % 2 == 0 else MUTED
            row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=8)
            row.pack(fill="x", pady=2)
            info = ctk.CTkFrame(row, fg_color=bg, corner_radius=0)
            info.pack(side="left", fill="x", expand=True, padx=14, pady=8)
            ctk.CTkLabel(info, text=item["title"],
                         font=("Helvetica", 11, "bold"), text_color=TEXT,
                         anchor="w").pack(fill="x")
            if item.get("description"):
                ctk.CTkLabel(info, text=item["description"][:90],
                             font=("Helvetica", 9), text_color=SUB,
                             anchor="w").pack(fill="x")
            ctk.CTkLabel(info, text=f"{len(item['urls'])} URL(s)",
                         font=("Helvetica", 8), text_color="#444466",
                         anchor="w").pack(fill="x")
            ctk.CTkButton(row, text="+ Add",
                          command=lambda it=item: self.app.add_from_catalog(it),
                          fg_color=ACCENT, hover_color=ACCENT_H,
                          width=80, height=30, font=("Helvetica", 9, "bold"),
                          corner_radius=6).pack(side="right", padx=12)


# ── Add game view ─────────────────────────────────────────────────────────────

class AddGameView(ctk.CTkFrame):
    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, fg_color=BG, corner_radius=0, **kw)
        self.app = app
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Add Game", font=("Helvetica", 22, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(24,12))

        form = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        form.pack(fill="x", padx=24, pady=(0,12))

        def field(label, var=None, text_widget=False, show=""):
            ctk.CTkLabel(form, text=label, font=("Helvetica", 9),
                         text_color=SUB).pack(anchor="w", padx=16, pady=(12,2))
            if text_widget:
                t = ctk.CTkTextbox(form, height=100, fg_color=BG,
                                   border_color=BORDER, border_width=1,
                                   font=("Helvetica", 10), text_color=TEXT,
                                   corner_radius=6)
                t.pack(fill="x", padx=16)
                return t
            e = ctk.CTkEntry(form, textvariable=var, show=show,
                             fg_color=BG, border_color=BORDER, text_color=TEXT,
                             font=("Helvetica", 10), corner_radius=6, height=36)
            e.pack(fill="x", padx=16)
            return e

        self._title_var = tk.StringVar()
        self._pw_var    = tk.StringVar()
        field("Game Title", self._title_var)
        self._urls_box = field("Direct Download URLs  (one per line)", text_widget=True)
        field("Archive Password (optional)", self._pw_var, show="*")

        ctk.CTkFrame(form, fg_color=CARD, height=8, corner_radius=0).pack()
        ctk.CTkButton(form, text="Add to Library", command=self._submit,
                      fg_color=ACCENT, hover_color=ACCENT_H, height=38,
                      font=("Helvetica", 10, "bold"), corner_radius=8,
                      ).pack(anchor="e", padx=16, pady=12)

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
        self.app.switch_view("library")


# ── Sidebar ───────────────────────────────────────────────────────────────────

class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, app: "GameHubApp", **kw):
        super().__init__(parent, fg_color=SIDEBAR, corner_radius=0,
                         width=220, **kw)
        self.pack_propagate(False)
        self.app = app
        self._items: dict[str, ctk.CTkButton] = {}
        self._build()

    def _build(self):
        # Logo
        logo = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0)
        logo.pack(fill="x", pady=(24, 8))
        ctk.CTkLabel(logo, text="🎮", font=("Helvetica", 34),
                     text_color=ACCENT).pack()
        ctk.CTkLabel(logo, text="GameHub", font=("Helvetica", 16, "bold"),
                     text_color=TEXT).pack()
        ctk.CTkLabel(logo, text="Game Library Manager",
                     font=("Helvetica", 8), text_color=SUB).pack()

        ctk.CTkFrame(self, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", padx=16, pady=12)

        for key, icon, label in [
            ("library",  "🎮", "Library"),
            ("catalog",  "📦", "Catalog"),
            ("add",      "➕", "Add Game"),
        ]:
            btn = ctk.CTkButton(
                self, text=f"  {icon}   {label}",
                anchor="w", font=("Helvetica", 11),
                fg_color=SIDEBAR, hover_color=CARD,
                text_color=SUB, height=44, corner_radius=8,
                command=lambda k=key: self.app.switch_view(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._items[key] = btn

        # Console toggle at bottom
        ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0).pack(
            fill="both", expand=True)
        ctk.CTkButton(
            self, text="  📋   Console",
            anchor="w", font=("Helvetica", 11),
            fg_color=SIDEBAR, hover_color=CARD,
            text_color=SUB, height=44, corner_radius=8,
            command=self.app.toggle_console,
        ).pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(self, text="v0.1.0", font=("Helvetica", 8),
                     text_color=MUTED).pack(pady=(0, 12))

    def set_active(self, key: str):
        for k, btn in self._items.items():
            if k == key:
                btn.configure(fg_color=CARD, text_color=TEXT)
            else:
                btn.configure(fg_color=SIDEBAR, text_color=SUB)


# ── Toast ─────────────────────────────────────────────────────────────────────

class _Toast(tk.Toplevel):
    def __init__(self, parent, msg: str):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg=ACCENT)
        tk.Label(self, text=msg, bg=ACCENT, fg=TEXT,
                 font=("Helvetica", 10), padx=20, pady=10).pack()
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width()  - self.winfo_width()  - 20
        py = parent.winfo_rooty() + parent.winfo_height() - self.winfo_height() - 60
        self.geometry(f"+{px}+{py}")
        self.after(2800, self.destroy)


# ── Main application ──────────────────────────────────────────────────────────

class GameHubApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GameHub")
        self.geometry("1300x860")
        self.minsize(980, 660)
        self.configure(fg_color=BG)

        self.store  = LibraryStore()
        self.games  = self.store.load()
        self._queue: queue.Queue[str] = queue.Queue()

        self.fetcher: CoverFetcher       = CoverFetcher(self.store.root / "covers")
        self._cover_images: dict[str, object] = {}
        self._cover_descs:  dict[str, str]    = {}

        self._views:    dict[str, ctk.CTkFrame] = {}
        self._active    = "library"

        self._build()
        self._refresh_library()
        self.after(250, self._drain)

    def _build(self):
        # Outer: sidebar | right
        outer = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        outer.pack(fill="both", expand=True)

        self.sidebar = Sidebar(outer, self)
        self.sidebar.pack(side="left", fill="y")

        right = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        # Views stacked
        view_area = ctk.CTkFrame(right, fg_color=BG, corner_radius=0)
        view_area.pack(fill="both", expand=True)

        for name, cls in [
            ("library", LibraryView),
            ("catalog", CatalogView),
            ("add",     AddGameView),
        ]:
            v = cls(view_area, self)
            v.place(relwidth=1, relheight=1)
            self._views[name] = v

        # Console panel at bottom of right column
        self.console = ConsolePanel(right)
        self.console.pack(fill="x", side="bottom")
        self.console.configure(height=200)
        self.console.pack_propagate(False)

        # Status bar
        self._status = ctk.CTkLabel(
            self, text="Ready", font=("Helvetica", 9),
            text_color=SUB, fg_color=SIDEBAR, anchor="w",
            corner_radius=0,
        )
        self._status.pack(fill="x", side="bottom", ipady=4, ipadx=12)

        self.switch_view("library")

    def switch_view(self, name: str):
        self.sidebar.set_active(name)
        for k, v in self._views.items():
            (v.lift if k == name else v.lower)()
        self._active = name

    def toggle_console(self):
        self.console.toggle()

    # ── Cover art ────────────────────────────────────────────────────────────

    def _cover_cb(self, gid: str, photo, desc: str):
        self.after(0, self._apply_cover, gid, photo, desc)

    def _apply_cover(self, gid: str, photo, desc: str):
        if photo:
            self._cover_images[gid] = photo
        if desc:
            self._cover_descs[gid] = desc
        self._views["library"].update_cover(gid, photo, desc)

    # ── Game ops ──────────────────────────────────────────────────────────────

    def add_game(self, title: str, urls: list[str], password: str = ""):
        self.games.append(GameEntry(title=title, urls=urls, password=password))
        self.store.save(self.games)
        self._refresh_library()
        _Toast(self, f'Added "{title}"')
        self.console.log(f'Game added: {title}', "ok")

    def add_from_catalog(self, item: dict):
        self.add_game(item["title"], item["urls"], item.get("password",""))

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
            self._sq()
            self.console.log(f"Downloading {game.title}…", "scrape")  # scheduled in drain
            paths = download_many(game.urls, game.download_dir(self.store.root),
                                  lambda m: self._queue.put(("log", m, "warn")))
            game.download_paths = [str(p) for p in paths]
            game.status = "downloaded"
            self._queue.put(("log", f"✓ Downloaded: {game.title}", "ok"))
        except Exception as exc:
            game.status = f"download failed: {exc}"
            self._queue.put(("log", f"✗ {game.title}: {exc}", "error"))
        finally:
            self._sq()

    def _install(self, game: GameEntry):
        try:
            paths   = [Path(p) for p in game.download_paths]
            archive = first_archive(paths)
            if not archive:
                raise RuntimeError("No supported archive found.")
            game.status = "installing"
            self._sq()
            dest = game.destination_dir(self.store.root)
            extract_archive(archive, dest, game.password)
            game.install_path = str(dest)
            game.status = "installed"
            self._queue.put(("log", f"✓ Installed: {game.title}", "ok"))
        except Exception as exc:
            game.status = f"install failed: {exc}"
            self._queue.put(("log", f"✗ {game.title}: {exc}", "error"))
        finally:
            self._sq()

    def _sq(self):
        self.store.save(self.games)
        self._queue.put(("refresh",))

    def _refresh_library(self):
        self._views["library"].refresh(self.games)

    def _drain(self):
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item[0] == "refresh":
                self._refresh_library()
            elif item[0] == "log":
                _, msg, tag = item
                self.console.log(msg, tag)
                self._status.configure(text=msg[:120])
        self.after(250, self._drain)


def main() -> None:
    GameHubApp().mainloop()


if __name__ == "__main__":
    main()
