"""Command line for the Raman intensity PID server.

    python -m kexp.util.guis.lasers.raman_intensity.cli status
    python -m kexp.util.guis.lasers.raman_intensity.cli hold on | off | toggle
    python -m kexp.util.guis.lasers.raman_intensity.cli release
    python -m kexp.util.guis.lasers.raman_intensity.cli clear
    python -m kexp.util.guis.lasers.raman_intensity.cli gains
    python -m kexp.util.guis.lasers.raman_intensity.cli set p1 -0.05
    python -m kexp.util.guis.lasers.raman_intensity.cli tail --seconds 5

Exit codes: 0 done; 1 refused / the board did not answer; 2 usage; 3 server not found.
"""

from __future__ import annotations

import sys

from kexp.util.guis.lasers.raman_intensity import SERVER_ID
from waxx.util.guis.intensity_pid.intensity_pid_cli import main as _main


def main(argv=None) -> int:
    return _main(argv, server_id=SERVER_ID, prog="raman_intensity")


if __name__ == "__main__":
    sys.exit(main())
