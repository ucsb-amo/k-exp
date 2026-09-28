"""The SLM spot finder, started from the Device Control GUI's SLM pill.

``launch_spot_finder`` does what ``calibrations/SLM_spot_finder/spot_finder.bat``
does -- this venv's python runs ``SLM_andor_main_gui.py`` in its folder, in a
console of its own that waits for a key when it exits (so a start-up error can
be read) -- detached from the GUI, on the PC the GUI runs on. The spot finder
finds its camera itself (liveOD's stream when liveOD serves it, else the Andor
opened here) and moves the APD stage only on a button.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

SPOT_FINDER_DIR = Path(__file__).resolve().parents[3] / "calibrations" / "SLM_spot_finder"
SPOT_FINDER_SCRIPT = "SLM_andor_main_gui.py"


def _console_python() -> str:
    """This venv's python.exe (the dashboard may run under pythonw.exe)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").is_file():
        return str(exe.with_name("python.exe"))
    return str(exe)


def spot_finder_command(python: str | None = None) -> str:
    """The command line: cmd runs the spot finder, then pauses.

    cmd /c strips the first and last quote of what follows it when there are
    more than two, hence the outer pair around the two quoted paths."""
    python = python or _console_python()
    script = SPOT_FINDER_DIR / SPOT_FINDER_SCRIPT
    return f'cmd.exe /c ""{python}" "{script}" & pause"'


def launch_spot_finder(popen=subprocess.Popen) -> str:
    """Start the spot finder; returns "console pid N on <host>" (the pid is
    cmd's). Raises if it is not there or cannot be started."""
    script = SPOT_FINDER_DIR / SPOT_FINDER_SCRIPT
    if not script.is_file():
        raise FileNotFoundError(f"no spot finder at {script}")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = popen(spot_finder_command(), cwd=str(SPOT_FINDER_DIR), creationflags=flags,
                 close_fds=True)
    try:
        host = socket.gethostname()
    except Exception:
        host = "this PC"
    return f"console pid {proc.pid} on {host}"
