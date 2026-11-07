"""The Raman beams' intensity stabilization on the K machine: a Quarto running
kexp/control/quarto/pid_intensity_stabilize_raman, served by the waxx
intensity PID server (``waxx.util.guis.intensity_pid``) with this machine's
port, id, loop names and folders.

Command line (agents, scripts)::

    python -m kexp.util.guis.lasers.raman_intensity.cli status
    python -m kexp.util.guis.lasers.raman_intensity.cli hold on
    python -m kexp.util.guis.lasers.raman_intensity.cli release
    python -m kexp.util.guis.lasers.raman_intensity.cli clear

From Python (host code, not inside a kernel)::

    from kexp.util.guis.lasers.raman_intensity import client
    c = client()
    c.hold(True); c.hold(False); c.clear(); c.status()
"""

import os

#: Discovery id of the server.
SERVER_ID = "raman_intensity"
TITLE = "Raman intensity"
#: Loop 1: IN1 photodiode, IN2 setpoint -> OUT1; loop 2: IN3, IN4 -> OUT2 (the sketch's comments).
LOOP_NAMES = ("80+ AOM", "150+ AOM")
#: The gains last set through the server (local disk on the PC the board is on).
GAINS_PATH = os.path.join(os.path.expanduser("~"), ".waxx", "raman_intensity", "gains.json")


def client(discovery_timeout: float = 3.0):
    """An IntensityPIDClient for this server (discovers it on the lab network)."""
    from waxx.util.guis.intensity_pid.intensity_pid_client import IntensityPIDClient  # noqa: PLC0415
    return IntensityPIDClient(SERVER_ID, discovery_timeout=discovery_timeout)
