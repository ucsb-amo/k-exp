"""Server registry: declares every server panel the dashboard knows about.

Each entry is a :class:`ServerSpec` describing how to launch the headless
server subprocess, what panel body to embed, what COM port to label (if any),
which discovery beacon id the server advertises, and how to build a client
for it (snapshot polling of the header badges + graceful shutdown at close).

Imports of panel/body factories and clients are *lazy* (deferred until the
entry is actually used) so the dashboard can still launch even if a module
fails to import.

Where a panel is placed by default lives in ``dashboard_layout.py``; the
``default_dock_area`` / ``default_placement`` here are only the fallback for
ids that file does not mention.

To add a new server: append a new ServerSpec to SERVER_SPECS (and, if it
should autostart on kong, add its id to ``dashboard_hosts.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from waxx.util.dashboard.panel_spec import ServerSpec
from kexp.config.ip import (
    ALS_COM,
    PRECILASER_COM,
    MAGNETOMETER_COM,
    INTERLOCK_COM,
    PDXC_COM,
)


_PY = sys.executable
_REPO = str(Path(__file__).resolve().parents[3])  # k-exp/kexp/util/dashboard -> repo root


def _lazy_panel(module_path: str, attr: str):
    """Return a body_factory that imports module_path lazily."""
    def factory():
        import importlib  # noqa: PLC0415
        mod = importlib.import_module(module_path)
        cls = getattr(mod, attr)
        return cls()
    return factory


def _lazy_client(module_path: str, attr: str, **kwargs):
    """Return a client_factory that imports and constructs the client lazily.

    Runs on a dashboard worker thread, so a 3 s discovery wait is fine.
    """
    def factory():
        import importlib  # noqa: PLC0415
        mod = importlib.import_module(module_path)
        cls = getattr(mod, attr)
        return cls(**kwargs)
    return factory


# ---------------------------------------------------------------------------
# Server specs
# ---------------------------------------------------------------------------

SERVER_SPECS: list[ServerSpec] = [
    ServerSpec(
        id="als",
        label="ALS Laser",
        icon="🔫",  # matches the standalone als_control_gui window icon
        body_factory=_lazy_panel("kexp.util.guis.lasers.als.als_panel", "AlsPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.lasers.als.als_server"],
        cwd=_REPO,
        server_id="als_laser",
        client_factory=_lazy_client("waxx.util.guis.als.als_gui_client", "ALSGuiClient",
                                    timeout_s=1.5, discovery_timeout=3.0),
        com_label=ALS_COM,
        warm_imports=["waxx.util.guis.als.als_control_gui"],
        default_dock_area="left",
    ),
    ServerSpec(
        id="precilaser",
        label="Precilaser",
        icon="💀",  # matches the standalone precilaser_control_gui window icon
        body_factory=_lazy_panel("kexp.util.guis.lasers.precilaser.precilaser_panel", "PrecilaserPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.lasers.precilaser.precilaser_server"],
        cwd=_REPO,
        server_id="precilaser",
        client_factory=_lazy_client("waxx.util.guis.precilaser.precilaser_gui_client", "PrecilaserGuiClient",
                                    timeout_s=1.5, discovery_timeout=3.0),
        com_label=PRECILASER_COM,
        warm_imports=["waxx.util.guis.precilaser.precilaser_control_gui"],
        default_dock_area="left",
    ),
    ServerSpec(
        id="monitor",
        label="Monitor",
        icon="👁",
        # Headless and panel-less: ready/not-ready state and the Start /
        # Restart / Stop controls live in the Device Control panel, so no
        # dock tile is needed.  The supervisor still runs in the background
        # and is listed in Running Servers and the Servers menu.
        body_factory=None,
        server_cmd=[_PY, "-m", "kexp.util.guis.device_state_gui.monitor_server_headless"],
        cwd=_REPO,
        graceful_stop_timeout_s=3.0,
        default_dock_area="bottom",
        hidden_panel=True,
    ),
    ServerSpec(
        id="magnetometer",
        label="HMR Magnetometer",
        icon="🧲",
        body_factory=_lazy_panel("kexp.util.guis.magnetic_field_monitor.magnetometer_panel", "MagnetometerPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.magnetic_field_monitor.magnetometer_hmr_server"],
        cwd=_REPO,
        server_id="magnetometer",
        client_factory=_lazy_client("waxx.util.guis.HMR_magnetometer.hmr_magnetometer_client", "HMRClient",
                                    discovery_timeout=3.0, timeout=1.5),
        com_label=MAGNETOMETER_COM,
        warm_imports=["pyqtgraph", "waxx.util.guis.HMR_magnetometer.hmr_magnetometer_gui"],
        default_dock_area="right",
        default_placement="tab",
        tab_group="diag",
    ),
    ServerSpec(
        id="bristol",
        label="Bristol Wavemeter",
        icon="〰",
        body_factory=_lazy_panel("kexp.util.guis.wavemeter_monitor.bristol.bristol_panel", "BristolServerPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.wavemeter_monitor.bristol.bristol_server"],
        cwd=_REPO,
        server_id="bristol_wavemeter",
        warm_imports=["pyqtgraph", "waxx.util.guis.bristol.bristol_wavemeter_client_gui"],
        default_dock_area="right",
        default_placement="tab",
        tab_group="diag",
    ),
    ServerSpec(
        id="basler",
        label="Basler Cameras",
        icon="📷",
        body_factory=_lazy_panel("kexp.util.guis.basler.basler_panel", "BaslerServerPanel"),
        # The embedded BaslerCamerasMainWindow is a ZMQ *client* that
        # discovers and connects to the headless server we spawn here.
        server_cmd=[_PY, "-m", "beacon.basler.server_headless"],
        cwd=_REPO,
        graceful_stop_timeout_s=3.0,
        warm_imports=["pyqtgraph", "numpy", "beacon.basler.cameras_gui"],
        default_dock_area="right",
    ),
    ServerSpec(
        id="keysight",
        label="Keysight Supplies",
        icon="🍌",
        body_factory=_lazy_panel("kexp.util.guis.keysight_monitor.keysight_panel", "KeysightServerPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.keysight_monitor.keysight_server_headless"],
        cwd=_REPO,
        server_id="keysight",
        warm_imports=["pyqtgraph", "waxx.util.guis.keysight.keysight_client_gui"],
        default_dock_area="right",
        default_placement="tab",
        tab_group="diag",
    ),
    ServerSpec(
        id="interlock",
        label="Interlock",
        icon="🔒",
        body_factory=_lazy_panel("kexp.util.guis.interlock.interlock_panel", "InterlockPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.interlock.interlock_server"],
        cwd=_REPO,
        server_id="interlock",
        client_factory=_lazy_client("kexp.util.guis.interlock.interlock_client", "InterlockClient",
                                    discovery_timeout=3.0, timeout=1.5),
        com_label=INTERLOCK_COM,
        graceful_stop_timeout_s=4.0,   # service joins its poll/watchdog threads
        warm_imports=["pyqtgraph"],
        default_dock_area="top",
    ),
    ServerSpec(
        id="pdxc",
        label="PDXC Picomotor",
        icon="⚙",
        body_factory=_lazy_panel("waxx.util.guis.pdxc.pdxc_client_gui", "PDXCClientWidget"),
        server_cmd=[_PY, "-m", "kexp.control.serial.server.pdxc_server"],
        cwd=_REPO,
        server_id="pdxc",
        client_factory=_lazy_client("waxx.control.misc.pdxc", "PDXC_Client",
                                    discovery_timeout=3.0, timeout=1.5),
        com_label=PDXC_COM,
        default_dock_area="right",
        default_placement="tab",
        tab_group="control",
    ),
    ServerSpec(
        id="tpi",
        label="TPI Signal Generators",
        icon="📻",
        # The embedded TpiDevicesMainWindow is a ZMQ client that discovers and
        # connects to the headless server we spawn here (like Basler).
        body_factory=_lazy_panel("waxx.util.guis.tpi.tpi_panel", "TpiServerPanel"),
        server_cmd=[_PY, "-m", "beacon.tpi.server"],
        cwd=_REPO,
        warm_imports=["waxx.util.guis.tpi.tpi_panel"],
        default_dock_area="right",
        default_placement="tab",
        tab_group="control",
    ),
]


def get_spec(server_id: str) -> Optional[ServerSpec]:
    for s in SERVER_SPECS:
        if s.id == server_id:
            return s
    return None


__all__ = ["SERVER_SPECS", "get_spec"]
