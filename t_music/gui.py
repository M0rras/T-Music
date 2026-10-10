"""Tkinter desktop window."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__
from .downloader import (ALL_FORMATS, AUDIO_QUALITIES, Downloader, DownloadOptions,
                         ProgressInfo, default_output_dir)

SETTINGS_FILE = Path.home() / ".t-music.json"


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"T-Music {__version__}")
        self.geometry("760x600")
        self.minsize(600, 480)

        settings = _load_settings()
        self.output_var = tk.StringVar(value=settings.get("output_dir", str(default_output_dir())))
        self.format_var = tk.StringVar(value=settings.get("format", "mp3"))
        self.quality_var = tk.StringVar(value=settings.get("quality", "192"))
        self.subfolder_var = tk.BooleanVar(value=settings.get("playlist_subfolder", True))
        self.thumb_var = tk.BooleanVar(value=settings.get("embed_thumbnail", True))
        self.status_var = tk.StringVar(value="Ready")

        self._events: queue.Queue = queue.Queue()
        self._downloader: Downloader | None = None
        self._worker: threading.Thread | None = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)

    # -- layout --------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="YouTube links (songs or playlists, one per line):").pack(anchor="w", **pad)
        self.urls_text = scrolledtext.ScrolledText(root, height=6, wrap="none")
        self.urls_text.pack(fill="x", **pad)

        out = ttk.Frame(root)
        out.pack(fill="x", **pad)
        ttk.Label(out, text="Save to:").pack(side="left")
        ttk.Entry(out, textvariable=self.output_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out, text="Browse…", command=self._browse).pack(side="left")
        ttk.Button(out, text="Open", command=self._open_folder).pack(side="left", padx=(6, 0))

        opts = ttk.Frame(root)
        opts.pack(fill="x", **pad)
        ttk.Label(opts, text="Format:").pack(side="left")
        ttk.Combobox(opts, textvariable=self.format_var, values=ALL_FORMATS, width=12,
                     state="readonly").pack(side="left", padx=(4, 12))
        ttk.Label(opts, text="Quality (kbps):").pack(side="left")
        ttk.Combobox(opts, textvariable=self.quality_var, values=AUDIO_QUALITIES, width=6,
                     state="readonly").pack(side="left", padx=(4, 12))
        ttk.Checkbutton(opts, text="Playlist sub-folder", variable=self.subfolder_var).pack(side="left")
        ttk.Checkbutton(opts, text="Cover art", variable=self.thumb_var).pack(side="left", padx=8)

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.download_btn = ttk.Button(btns, text="Download", command=self._start)
        self.download_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Clear log", command=self._clear_log).pack(side="right")

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", **pad)
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", **pad)

        self.log_text = scrolledtext.ScrolledText(root, height=12, state="disabled")
        self.log_text.pack(fill="both", expand=True, **pad)

    # -- actions -------------------------------------------------------------

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.home()))
        if folder:
            self.output_var.set(folder)

    def _open_folder(self) -> None:
        folder = Path(self.output_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - opening a folder in Explorer
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _start(self) -> None:
        urls = [u for u in self.urls_text.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("T-Music", "Paste at least one YouTube link.")
            return
        options = DownloadOptions(
            output_dir=Path(self.output_var.get()).expanduser(),
            audio_format=self.format_var.get(),
            audio_quality=self.quality_var.get(),
            playlist_subfolder=self.subfolder_var.get(),
            embed_thumbnail=self.thumb_var.get(),
        )
        _save_settings({
            "output_dir": str(options.output_dir),
            "format": options.audio_format,
            "quality": options.audio_quality,
            "playlist_subfolder": options.playlist_subfolder,
            "embed_thumbnail": options.embed_thumbnail,
        })
        self._downloader = Downloader(
            options,
            log=lambda m: self._events.put(("log", m)),
            progress=lambda p: self._events.put(("progress", p)),
        )
        self.download_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress["value"] = 0
        self.status_var.set("Starting…")
        self._worker = threading.Thread(target=self._run, args=(urls,), daemon=True)
        self._worker.start()

    def _run(self, urls: list[str]) -> None:
        try:
            summary = self._downloader.download(urls)
            self._events.put(("done", str(summary)))
        except Exception as exc:  # surface unexpected errors instead of dying silently
            self._events.put(("log", f"ERROR: {exc}"))
            self._events.put(("done", "Failed"))

    def _cancel(self) -> None:
        if self._downloader:
            self._downloader.cancel()
            self.status_var.set("Cancelling…")
            self.cancel_btn.config(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno("T-Music", "A download is running. Quit anyway?"):
                return
            self._downloader.cancel()
        self.destroy()

    # -- worker -> UI ----------------------------------------------------------

    def _append_log(self, msg: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    self._show_progress(payload)
                elif kind == "done":
                    self.status_var.set(payload)
                    self.progress["value"] = 0
                    self.download_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _show_progress(self, p: ProgressInfo) -> None:
        if p.status == "downloading":
            if p.percent is not None:
                self.progress["value"] = p.percent
            extra = f" — {p.percent:.0f}%" if p.percent is not None else ""
            if p.speed:
                extra += f" at {p.speed}, ETA {p.eta}"
            self.status_var.set(f"Downloading: {p.title}{extra}")
        elif p.status == "converting":
            self.status_var.set(f"Converting: {p.title}")
        elif p.status == "finished":
            self.progress["value"] = 100


def main() -> int:
    App().mainloop()
    return 0
