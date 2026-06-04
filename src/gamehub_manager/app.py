from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gamehub_manager.catalog import CatalogItem, load_catalog
from gamehub_manager.downloader import download_many
from gamehub_manager.installer import extract_archive, first_archive
from gamehub_manager.library import LibraryStore
from gamehub_manager.models import GameEntry


class GameHubApp(tk.Tk):
    """Tkinter desktop UI for managing lawful game downloads."""

    def __init__(self) -> None:
        super().__init__()
        self.title("GameHub Manager")
        self.geometry("900x620")
        self.store = LibraryStore()
        self.games = self.store.load()
        self.catalog_items: list[CatalogItem] = []
        self.messages: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self._refresh_games()
        self.after(250, self._drain_messages)

    def _build_ui(self) -> None:
        notice = (
            "Use only direct download URLs you are authorized to access. "
            "This app does not bypass shorteners, captchas, or access controls."
        )
        ttk.Label(self, text=notice, wraplength=860).pack(fill="x", padx=12, pady=(12, 6))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=6)

        library_tab = ttk.Frame(notebook)
        catalog_tab = ttk.Frame(notebook)
        notebook.add(library_tab, text="Library")
        notebook.add(catalog_tab, text="Catalog")

        input_frame = ttk.LabelFrame(library_tab, text="Add game")
        input_frame.pack(fill="x", padx=0, pady=6)
        ttk.Label(input_frame, text="Title").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.title_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.title_var).grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(input_frame, text="Archive password (optional)").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.password_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.password_var, show="*").grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(input_frame, text="Direct URLs (one per line)").grid(row=2, column=0, sticky="nw", padx=8, pady=4)
        self.urls_text = tk.Text(input_frame, height=5)
        self.urls_text.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(input_frame, text="Add to Library", command=self._add_game).grid(row=3, column=1, sticky="e", padx=8, pady=8)
        input_frame.columnconfigure(1, weight=1)

        library_frame = ttk.LabelFrame(library_tab, text="Library")
        library_frame.pack(fill="both", expand=True, padx=0, pady=6)
        self.tree = ttk.Treeview(library_frame, columns=("status", "files", "install"), show="headings", selectmode="browse")
        self.tree.heading("status", text="Status")
        self.tree.heading("files", text="Files")
        self.tree.heading("install", text="Install path")
        self.tree.column("status", width=180)
        self.tree.column("files", width=80)
        self.tree.column("install", width=420)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        actions = ttk.Frame(library_tab)
        actions.pack(fill="x", padx=0, pady=6)
        ttk.Button(actions, text="Download Selected", command=self._download_selected).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Install / Extract Selected", command=self._install_selected).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Remove Selected", command=self._remove_selected).pack(side="left")

        self._build_catalog_tab(catalog_tab)

        self.log = tk.Text(self, height=8, state="disabled")
        self.log.pack(fill="x", padx=12, pady=(6, 12))

    def _build_catalog_tab(self, parent: ttk.Frame) -> None:
        help_text = (
            "Load a JSON catalog from a local file or authorized HTTP(S) URL. "
            "Catalog entries must contain direct URLs you have the right to download."
        )
        ttk.Label(parent, text=help_text, wraplength=840).pack(fill="x", pady=(6, 8))

        source_frame = ttk.Frame(parent)
        source_frame.pack(fill="x", pady=4)
        self.catalog_source_var = tk.StringVar()
        ttk.Entry(source_frame, textvariable=self.catalog_source_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(source_frame, text="Browse", command=self._browse_catalog).pack(side="left", padx=(0, 8))
        ttk.Button(source_frame, text="Load Catalog", command=self._load_catalog).pack(side="left")

        self.catalog_tree = ttk.Treeview(
            parent,
            columns=("title", "description", "files"),
            show="headings",
            selectmode="browse",
        )
        self.catalog_tree.heading("title", text="Title")
        self.catalog_tree.heading("description", text="Description")
        self.catalog_tree.heading("files", text="Files")
        self.catalog_tree.column("title", width=260)
        self.catalog_tree.column("description", width=440)
        self.catalog_tree.column("files", width=80)
        self.catalog_tree.pack(fill="both", expand=True, pady=8)

        catalog_actions = ttk.Frame(parent)
        catalog_actions.pack(fill="x")
        ttk.Button(catalog_actions, text="Add Selected to Library", command=self._add_catalog_selection).pack(side="left")

    def _browse_catalog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open catalog JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if path:
            self.catalog_source_var.set(path)

    def _load_catalog(self) -> None:
        source = self.catalog_source_var.get().strip()
        if not source:
            messagebox.showerror("GameHub Manager", "Choose a catalog JSON file or URL first.")
            return
        try:
            self.catalog_items = load_catalog(source)
        except Exception as exc:
            messagebox.showerror("GameHub Manager", f"Could not load catalog: {exc}")
            return
        self.catalog_tree.delete(*self.catalog_tree.get_children())
        for index, item in enumerate(self.catalog_items):
            self.catalog_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(item.title, item.description, len(item.urls)),
            )
        self.messages.put(f"Loaded {len(self.catalog_items)} catalog title(s).")

    def _add_catalog_selection(self) -> None:
        selection = self.catalog_tree.selection()
        if not selection:
            messagebox.showinfo("GameHub Manager", "Select a catalog title first.")
            return
        item = self.catalog_items[int(selection[0])]
        self.games.append(GameEntry(title=item.title, urls=item.urls, password=item.password))
        self.store.save(self.games)
        self._refresh_games()
        self.messages.put(f"Added {item.title} to the library.")

    def _selected_game(self) -> GameEntry | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("GameHub Manager", "Select a game first.")
            return None
        game_id = selection[0]
        return next((game for game in self.games if game.game_id == game_id), None)

    def _add_game(self) -> None:
        title = self.title_var.get().strip()
        urls = [line.strip() for line in self.urls_text.get("1.0", "end").splitlines() if line.strip()]
        if not title or not urls:
            messagebox.showerror("GameHub Manager", "A title and at least one direct URL are required.")
            return
        self.games.append(GameEntry(title=title, urls=urls, password=self.password_var.get()))
        self.store.save(self.games)
        self.title_var.set("")
        self.password_var.set("")
        self.urls_text.delete("1.0", "end")
        self._refresh_games()

    def _download_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._run_background(lambda: self._download_game(game))

    def _download_game(self, game: GameEntry) -> None:
        try:
            game.status = "downloading"
            self._save_and_refresh()
            paths = download_many(game.urls, game.download_dir(self.store.root), self.messages.put)
            game.download_paths = [str(path) for path in paths]
            game.status = "downloaded"
            self.messages.put(f"Downloaded {game.title}")
        except Exception as exc:
            game.status = f"download failed: {exc}"
            self.messages.put(game.status)
        finally:
            self._save_and_refresh()

    def _install_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._run_background(lambda: self._install_game(game))

    def _install_game(self, game: GameEntry) -> None:
        try:
            paths = [Path(path) for path in game.download_paths]
            archive = first_archive(paths)
            if archive is None:
                raise RuntimeError("No supported archive was downloaded.")
            game.status = "installing"
            self._save_and_refresh()
            destination = game.destination_dir(self.store.root)
            extract_archive(archive, destination, game.password)
            game.install_path = str(destination)
            game.status = "installed"
            self.messages.put(f"Installed {game.title} to {destination}")
        except Exception as exc:
            game.status = f"install failed: {exc}"
            self.messages.put(game.status)
        finally:
            self._save_and_refresh()

    def _remove_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.games = [item for item in self.games if item.game_id != game.game_id]
        self.store.save(self.games)
        self._refresh_games()

    def _run_background(self, target) -> None:
        threading.Thread(target=target, daemon=True).start()

    def _save_and_refresh(self) -> None:
        self.store.save(self.games)
        self.messages.put("__refresh__")

    def _refresh_games(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for game in self.games:
            self.tree.insert("", "end", iid=game.game_id, values=(game.status, len(game.download_paths), game.install_path))

    def _drain_messages(self) -> None:
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            if message == "__refresh__":
                self._refresh_games()
            else:
                self.log.configure(state="normal")
                self.log.insert("end", message + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        self.after(250, self._drain_messages)


def main() -> None:
    app = GameHubApp()
    app.mainloop()


if __name__ == "__main__":
    main()
