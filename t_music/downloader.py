"""Core download logic built on yt-dlp.

This module has no GUI dependencies so it can be used from the CLI, the GUI
and the tests alike.

Skipping already-downloaded songs works in two layers:

1. A download archive (``.t-music-archive.txt`` in the output folder) records
   the YouTube ID of every finished song. yt-dlp checks it *before* touching
   the network for a video, so re-running a big playlist is fast.
2. If the archive is missing or was deleted, a match filter checks whether the
   final audio file already exists on disk. If it does, the song is skipped and
   its ID is added to the archive so the next run is instant.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import yt_dlp
from yt_dlp.utils import DownloadCancelled

ARCHIVE_FILENAME = ".t-music-archive.txt"

AUDIO_FORMATS = ("mp3", "m4a", "opus", "flac", "wav")
VIDEO_FORMAT = "mp4 (video)"
ALL_FORMATS = AUDIO_FORMATS + (VIDEO_FORMAT,)
AUDIO_QUALITIES = ("320", "256", "192", "128")

# Songs from a playlist go into a sub-folder named after the playlist;
# single songs go straight into the output folder.
SINGLE_TEMPLATE = "%(title)s.%(ext)s"
PLAYLIST_TEMPLATE = "%(playlist_title)s/%(title)s.%(ext)s"

# Formats that cannot carry an embedded cover image.
_NO_THUMBNAIL_FORMATS = {"wav"}

LogFn = Callable[[str], None]
ProgressFn = Callable[["ProgressInfo"], None]


@dataclass
class DownloadOptions:
    output_dir: Path
    audio_format: str = "mp3"
    audio_quality: str = "192"
    playlist_subfolder: bool = True
    embed_metadata: bool = True
    embed_thumbnail: bool = True

    @property
    def is_video(self) -> bool:
        return self.audio_format == VIDEO_FORMAT

    @property
    def final_ext(self) -> str:
        return "mp4" if self.is_video else self.audio_format


@dataclass
class ProgressInfo:
    title: str
    percent: float | None
    speed: str
    eta: str
    status: str  # "downloading", "finished", "converting"


@dataclass
class DownloadSummary:
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"{len(self.downloaded)} downloaded, {len(self.skipped)} skipped "
                f"(already downloaded), {len(self.failed)} failed")


def resource_dir() -> Path:
    """Directory holding bundled files (PyInstaller's temp dir when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def _find_tool(name: str) -> Path | None:
    """Locate a helper program: bundled copy first, then ./vendor, then PATH."""
    exe = f"{name}.exe" if os.name == "nt" else name
    for candidate in (resource_dir() / exe, resource_dir() / "vendor" / exe):
        if candidate.is_file():
            return candidate
    on_path = shutil.which(name)
    return Path(on_path) if on_path else None


def find_ffmpeg() -> str | None:
    """Directory containing ffmpeg (for yt-dlp's ``ffmpeg_location``), or None."""
    path = _find_tool("ffmpeg")
    return str(path.parent) if path else None


def find_deno() -> str | None:
    """Path to deno, which yt-dlp needs to solve YouTube's JavaScript challenges."""
    path = _find_tool("deno")
    if path is None:
        try:
            import deno  # the PyPI "deno" package ships the binary
            path = Path(deno.find_deno_bin())
        except Exception:
            return None
    return str(path)


def default_output_dir() -> Path:
    music = Path.home() / "Music"
    return (music if music.is_dir() else Path.home()) / "T-Music"


class _Logger:
    """Routes yt-dlp messages to our log callback and tracks archive skips."""

    def __init__(self, log: LogFn, summary: DownloadSummary):
        self._log = log
        self._summary = summary

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            return
        if "has already been recorded in the archive" in msg:
            # "[download] <title> has already been recorded in the archive"
            title = msg.removeprefix("[download] ").split(" has already been recorded")[0].rstrip(":")
            self._summary.skipped.append(title)
            self._log(f"Skipping (already downloaded): {title}")
            return
        if msg.startswith("[download]") and "%" in msg:
            return  # progress lines are reported through the progress hook
        self._log(msg)

    def info(self, msg: str) -> None:
        self.debug(msg)

    def warning(self, msg: str) -> None:
        self._log(f"WARNING: {msg}")

    def error(self, msg: str) -> None:
        self._summary.failed.append(msg)
        self._log(msg)


class Downloader:
    def __init__(self, options: DownloadOptions, log: LogFn = print,
                 progress: ProgressFn | None = None):
        self.options = options
        self.log = log
        self.progress = progress
        self._cancel = threading.Event()
        self.ffmpeg_location = find_ffmpeg()
        self.deno_path = find_deno()

    def cancel(self) -> None:
        self._cancel.set()

    # -- yt-dlp configuration -------------------------------------------------

    def _build_params(self, summary: DownloadSummary) -> dict:
        opts = self.options
        params: dict = {
            "paths": {"home": str(opts.output_dir)},
            "outtmpl": {"default": SINGLE_TEMPLATE},
            "download_archive": str(opts.output_dir / ARCHIVE_FILENAME),
            "ignoreerrors": True,   # keep going when one song in a playlist fails
            "noplaylist": False,
            "windowsfilenames": True,
            "overwrites": False,
            "logger": _Logger(self.log, summary),
            "progress_hooks": [self._on_progress],
            "postprocessor_hooks": [self._on_postprocess],
            "post_hooks": [lambda path: summary.downloaded.append(Path(path).stem)],
            "match_filter": self._make_existing_file_filter(summary),
            "writethumbnail": opts.embed_thumbnail and opts.final_ext not in _NO_THUMBNAIL_FORMATS,
        }
        if self.ffmpeg_location:
            params["ffmpeg_location"] = self.ffmpeg_location
        if self.deno_path:
            params["js_runtimes"] = {"deno": {"path": self.deno_path}}

        postprocessors: list[dict] = []
        if opts.is_video:
            params["format"] = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
            params["merge_output_format"] = "mp4"
        else:
            params["format"] = "bestaudio/best"
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": opts.audio_format,
                "preferredquality": opts.audio_quality,
            })
        if opts.embed_metadata:
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
        if params["writethumbnail"]:
            # Square-ish JPG covers work in every player.
            postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg",
                                   "when": "before_dl"})
            postprocessors.append({"key": "EmbedThumbnail"})
        params["postprocessors"] = postprocessors
        return params

    def _make_existing_file_filter(self, summary: DownloadSummary):
        """Skip songs whose final file is already on disk (archive fallback)."""
        holder: dict = {}
        self._filter_holder = holder

        def _filter(info: dict, *, incomplete: bool) -> str | None:
            if self._cancel.is_set():
                raise DownloadCancelled("Cancelled by user")
            ydl = holder.get("ydl")
            if incomplete or ydl is None:
                return None  # wait for full info before deciding
            existing = self.expected_path(ydl, info)
            if existing is not None and existing.exists():
                title = info.get("title") or info.get("id", "?")
                summary.skipped.append(title)
                ydl.record_download_archive(info)
                return f"Skipping (file already exists): {existing.name}"
            return None

        return _filter

    def use_template(self, ydl: yt_dlp.YoutubeDL, is_playlist: bool) -> None:
        use_folder = is_playlist and self.options.playlist_subfolder
        ydl.params["outtmpl"]["default"] = PLAYLIST_TEMPLATE if use_folder else SINGLE_TEMPLATE

    def expected_path(self, ydl: yt_dlp.YoutubeDL, info: dict) -> Path | None:
        try:
            name = ydl.prepare_filename(info)
        except Exception:
            return None
        if not name:
            return None
        return Path(name).with_suffix("." + self.options.final_ext)

    # -- hooks ---------------------------------------------------------------

    def _on_progress(self, d: dict) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled("Cancelled by user")
        if not self.progress:
            return
        info = d.get("info_dict") or {}
        title = info.get("title") or Path(d.get("filename", "")).stem
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            percent = (done / total * 100) if total else None
            self.progress(ProgressInfo(title, percent, (d.get("_speed_str") or "").strip(),
                                       (d.get("_eta_str") or "").strip(), "downloading"))
        elif d["status"] == "finished":
            self.progress(ProgressInfo(title, 100.0, "", "", "finished"))

    def _on_postprocess(self, d: dict) -> None:
        if self.progress and d["status"] == "started" and d.get("postprocessor") == "ExtractAudio":
            title = (d.get("info_dict") or {}).get("title", "")
            self.progress(ProgressInfo(title, None, "", "", "converting"))

    # -- public API ------------------------------------------------------------

    def download(self, urls: Iterable[str]) -> DownloadSummary:
        urls = [u.strip() for u in urls if u and u.strip()]
        summary = DownloadSummary()
        if not urls:
            self.log("No URLs given.")
            return summary
        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.ffmpeg_location:
            self.log("WARNING: ffmpeg was not found; audio conversion will fail. "
                     "Run 'python build.py --fetch-tools' or install ffmpeg.")

        with yt_dlp.YoutubeDL(self._build_params(summary)) as ydl:
            self._filter_holder["ydl"] = ydl
            for url in urls:
                if self._cancel.is_set():
                    break
                self.log(f"Processing: {url}")
                try:
                    # Resolve the URL first (no extra request) so we know whether
                    # it is a playlist and can pick the output folder layout.
                    info = ydl.extract_info(url, download=False, process=False)
                    if info is None:  # error already reported by yt-dlp
                        continue
                    self.use_template(ydl, info.get("_type") in ("playlist", "multi_video"))
                    ydl.process_ie_result(info, download=True)
                except DownloadCancelled:
                    self.log("Download cancelled.")
                    break
                except Exception as exc:  # keep going with the remaining URLs
                    summary.failed.append(f"{url}: {exc}")
                    self.log(f"ERROR: {url}: {exc}")
        self.log(f"Done: {summary}")
        return summary
