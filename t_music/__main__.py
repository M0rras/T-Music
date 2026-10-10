"""Entry point: opens the GUI with no arguments, runs the CLI otherwise."""

import os
import sys


def _fix_std_streams(cli: bool) -> None:
    """The .exe is built without a console window, so stdout/stderr are None.

    For CLI use we attach to the console of the terminal that launched us;
    otherwise we point the streams at devnull so libraries that print don't crash.
    """
    if cli and sys.platform == "win32" and sys.stdout is None:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
            sys.stderr = sys.stdout
            print()
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def main() -> int:
    cli = len(sys.argv) > 1
    _fix_std_streams(cli)
    if cli:
        from t_music.cli import main as cli_main
        return cli_main()
    from t_music.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
