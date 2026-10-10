# T-Music

A small desktop app for downloading a single YouTube song or a whole playlist as
audio files (MP3 by default). It ships as one `T-Music.exe`. Nothing needs to be
installed on the PC that runs it: Python, ffmpeg and deno are all bundled inside.

> Only download content you own or have permission to download, and follow
> YouTube's Terms of Service.

## Features

- Paste one or more links (single videos or playlists), one per line
- MP3, M4A, Opus, FLAC or WAV audio, or MP4 video
- Choose the bitrate (128–320 kbps)
- Embeds title/artist tags and cover art
- Playlists are saved into a folder named after the playlist
- **Skips songs you already have**, so you can re-run a playlist to fetch only the new songs
- If one song in a playlist is unavailable, the rest still download
- Cancel button and a progress bar; remembers your last settings
- Also works from the command line

## How the "already downloaded" skip works

1. **Download archive**: every finished song's YouTube ID is written to
   `.t-music-archive.txt` in the output folder. On the next run those IDs are
   skipped before anything is downloaded, which keeps re-running a large
   playlist fast.
2. **Existing-file check**: if the archive is missing (deleted, or the songs came
   from somewhere else), T-Music works out each song's final filename. If that
   file already exists, the song is skipped and added to the archive.

To force a song to download again, delete its file *and* its line in
`.t-music-archive.txt`.

## Getting the .exe

### Option A: let GitHub build it (no Windows build tools needed)

Every push runs `.github/workflows/build.yml` on a Windows runner. Open the
**Actions** tab, select the latest run and download the **T-Music-windows**
artifact. Pushing a tag such as `v1.0.0` also attaches `T-Music.exe` to a GitHub
Release.

### Option B: build it yourself on Windows

You need Python 3.10+ on the build machine only. Double-click `build.bat`, or run:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-build.txt
python build.py
```

The result is `dist\T-Music.exe`. Copy that one file to any Windows 10/11 PC
and run it.

## Usage

Double-click `T-Music.exe` to open the window. Paste links, pick a folder and
click **Download**.

Command line (from `cmd` or PowerShell):

```bat
T-Music.exe "https://www.youtube.com/playlist?list=..." -o D:\Music
T-Music.exe URL1 URL2 --format m4a --quality 256
T-Music.exe -f links.txt            :: one URL per line, # for comments
T-Music.exe --help
```

## Development

```bash
pip install -r requirements-build.txt
python build.py --fetch-tools     # copies ffmpeg + deno into ./vendor
python run.py                     # GUI
python run.py <url>               # CLI
python -m unittest discover -s tests
```

YouTube changes often. If downloads start failing, rebuild with the latest
yt-dlp (`pip install -U "yt-dlp[default,deno]"` then `python build.py`).

## Project layout

| Path | Purpose |
|---|---|
| `t_music/downloader.py` | Core logic: yt-dlp options, skip logic, progress |
| `t_music/gui.py` | Tkinter window |
| `t_music/cli.py` | Command-line interface |
| `run.py` | Entry point (GUI without arguments, CLI with them) |
| `build.py` / `build.bat` | PyInstaller one-file build with bundled ffmpeg and deno |
| `tests/` | Unit tests for the skip logic |
