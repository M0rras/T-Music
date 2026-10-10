"""Build a single self-contained T-Music executable with PyInstaller.

    pip install -r requirements-build.txt
    python build.py

The result is dist/T-Music.exe on Windows (dist/T-Music elsewhere). ffmpeg and
deno (needed by yt-dlp for YouTube) are bundled inside it, so the end user
doesn't need to install anything.

    python build.py --fetch-tools   # only copy ffmpeg/deno into ./vendor (for dev runs)
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
EXE = ".exe" if os.name == "nt" else ""


def _vendor_copy(name: str, source: Path) -> Path:
    target = VENDOR / f"{name}{EXE}"
    if target.is_file():
        print(f"{name} already present: {target}")
        return target
    VENDOR.mkdir(exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    print(f"Copied {name}: {source} -> {target}")
    return target


def fetch_tools() -> list[Path]:
    """Copy ffmpeg (from imageio-ffmpeg) and deno (from the deno package) into ./vendor."""
    try:
        import deno
        import imageio_ffmpeg
    except ImportError as exc:
        sys.exit(f"{exc.name} is missing: pip install -r requirements-build.txt")
    return [
        _vendor_copy("ffmpeg", Path(imageio_ffmpeg.get_ffmpeg_exe())),
        _vendor_copy("deno", Path(deno.find_deno_bin())),
    ]


def build() -> None:
    tools = fetch_tools()
    import PyInstaller.__main__

    sep = os.pathsep  # PyInstaller's src/dest separator for --add-binary
    PyInstaller.__main__.run([
        str(ROOT / "run.py"),
        "--name", "T-Music",
        "--onefile",
        "--windowed",      # no console window for the GUI
        "--noconfirm",
        "--clean",
        *[arg for tool in tools for arg in ("--add-binary", f"{tool}{sep}.")],
        "--collect-submodules", "yt_dlp",   # extractors are imported lazily
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ])
    exe = ROOT / "dist" / ("T-Music.exe" if os.name == "nt" else "T-Music")
    print(f"\nBuilt: {exe}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-tools", action="store_true",
                        help="only copy ffmpeg and deno into ./vendor, don't build")
    args = parser.parse_args()
    fetch_tools() if args.fetch_tools else build()
