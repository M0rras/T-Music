"""Command-line interface: ``T-Music.exe <url> [<url> ...] [options]``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .downloader import (ALL_FORMATS, AUDIO_QUALITIES, Downloader, DownloadOptions,
                         ProgressInfo, default_output_dir)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="T-Music",
        description="Download YouTube songs or whole playlists as audio files. "
                    "Songs that were already downloaded are skipped.")
    p.add_argument("urls", nargs="*", help="video or playlist URLs")
    p.add_argument("-f", "--file", type=Path, help="text file with one URL per line")
    p.add_argument("-o", "--output", type=Path, default=default_output_dir(),
                   help="output folder (default: %(default)s)")
    p.add_argument("--format", choices=[f.split()[0] for f in ALL_FORMATS], default="mp3",
                   help="audio format, or mp4 for video (default: mp3)")
    p.add_argument("--quality", choices=AUDIO_QUALITIES, default="192",
                   help="audio bitrate in kbps (default: 192)")
    p.add_argument("--no-subfolder", action="store_true",
                   help="don't put playlist songs in a folder named after the playlist")
    p.add_argument("--no-thumbnail", action="store_true", help="don't embed cover art")
    p.add_argument("--no-metadata", action="store_true", help="don't embed tags")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _print_progress(p: ProgressInfo) -> None:
    if p.status == "downloading" and p.percent is not None:
        sys.stdout.write(f"\r  {p.percent:5.1f}%  {p.speed:>12}  ETA {p.eta:<8}")
        sys.stdout.flush()
    elif p.status == "finished":
        sys.stdout.write("\r  100.0%" + " " * 30 + "\n")
    elif p.status == "converting":
        print(f"  Converting: {p.title}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    urls = list(args.urls)
    if args.file:
        urls += [line.strip() for line in args.file.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
    if not urls:
        build_parser().print_help()
        return 2

    fmt = "mp4 (video)" if args.format == "mp4" else args.format
    options = DownloadOptions(
        output_dir=args.output,
        audio_format=fmt,
        audio_quality=args.quality,
        playlist_subfolder=not args.no_subfolder,
        embed_metadata=not args.no_metadata,
        embed_thumbnail=not args.no_thumbnail,
    )
    downloader = Downloader(options, log=print, progress=_print_progress)
    try:
        summary = downloader.download(urls)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    return 1 if summary.failed and not summary.downloaded else 0
