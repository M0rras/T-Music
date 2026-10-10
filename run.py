"""Launcher used for `python run.py` and as the PyInstaller entry script."""

import sys

from t_music.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
