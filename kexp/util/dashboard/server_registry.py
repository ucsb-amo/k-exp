"""Server registry: declares every server panel the dashboard knows about.

Each entry is a :class:`ServerSpec` describing how to launch the headless
server subprocess, what panel body to embed, what COM port to label (if any),
and where the server's snapshot/RPC socket lives.

Imports of panel/body factories are *lazy* (deferred until the entry is
actually used) so the dashboard can still launch even if a panel module
fails to import.  Each spec's ``body_factory`` is a small lambda that does
the import inside.

To add a new server: append a new ServerSpec to SERVER_SPECS.
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


# ---------------------------------------------------------------------------
# Server specs
# ---------------------------------------------------------------------------

SERVER_SPECS: list[ServerSpec] = [
    ServerSpec(
        id="als",
        label="ALS Laser",
        body_factory=_lazy_panel("kexp.util.guis.lasers.als.als_panel", "AlsPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.lasers.als.als_server"],
        cwd=_REPO,
        com_label=ALS_COM,
        graceful_stop_timeout_s=5.0,
        restart_on_crash=False,
        default_dock_area="left",
        default_placement="dock",
    ),
    ServerSpec(
        id="precilaser",
        label="Precilaser",
        body_factory=_lazy_panel("kexp.util.guis.lasers.precilaser.precilaser_panel", "PrecilaserPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.lasers.precilaser.precilaser_server"],
        cwd=_REPO,
        com_label=PRECILASER_COM,
        graceful_stop_timeout_s=5.0,
        restart_on_crash=False,
        default_dock_area="left",
        default_placement="dock",
    ),
    ServerSpec(
        id="monitor",
        label="Monitor",
        # Headless and panel-less: ready/not-ready state is shown by the
        # Device Control GUI, so neither a Qt window nor a dashboard tile
        # is needed. The supervisor still runs in the background and is
        # listed in the Running Servers overview.
        body_factory=None,
        server_cmd=[_PY, "-m", "kexp.util.guis.device_state_gui.monitor_server_headless"],
        cwd=_REPO,
        graceful_stop_timeout_s=8.0,
        restart_on_crash=False,
        default_dock_area="bottom",
        default_placement="dock",
        hidden_panel=True,
    ),
    ServerSpec(
        id="magnetometer",
        label="HMR Magnetometer",
        body_factory=_lazy_panel("kexp.util.guis.magnetic_field_monitor.magnetometer_panel", "MagnetometerPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.magnetic_field_monitor.magnetometer_hmr_server"],
        cwd=_REPO,
        com_label=MAGNETOMETER_COM,
        graceful_stop_timeout_s=5.0,
        restart_on_crash=False,
        default_dock_area="right",
        default_placement="tab",
        tab_group="diag",
    ),
    ServerSpec(
        id="bristol",
        label="Bristol Wavemeter",
        body_factory=_lazy_panel("kexp.util.guis.wavemeter_monitor.bristol.bristol_panel", "BristolServerPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.wavemeter_monitor.bristol.bristol_server"],
        cwd=_REPO,
        com_label="LAN",
        graceful_stop_timeout_s=5.0,
        restart_on_crash=False,
        default_dock_area="right",
        default_placement="tab",
        tab_group="diag",
    ),
    ServerSpec(
        id="basler",
        label="Basler Cameras",
        body_factory=_lazy_panel("kexp.util.guis.basler.basler_panel", "BaslerServerPanel"),
        # The embedded BaslerCamerasMainWindow is a ZMQ *client* that
        # discovers and connects to the headless server we spawn here.
        server_cmd=[_PY, "-m", "kexp.util.guis.basler.basler_server_headless"],
        cwd=_REPO,
        graceful_stop_timeout_s=10.0,
        restart_on_crash=False,
        default_dock_area="right",
        default_placement="dock",
    ),
    ServerSpec(
        id="keysight",
        label="Keysight Supplies",
        # Embeds the thin client widget (KeysightServerPanel == KeysightClientPanel)
        # that talks to the headless KeysightServer over TCP.  No dashboard
        # opens a VXI11 connection to the supplies directly.
        body_factory=_lazy_panel(
            "kexp.util.guis.keysight_monitor.keysight_panel",
            "KeysightServerPanel",
        ),
        server_cmd=[_PY, "-m", "kexp.util.guis.keysight_monitor.keysight_server_headless"],
        cwd=_REPO,
        com_label="LAN",
        graceful_stop_timeout_s=5.0,
        restart_on_crash=False,
        default_dock_area="right",
        default_placement="tab",
        tab_group="diag",
    ),
    ServerSpec(
        id="interlock",
        label="Interlock",
        body_factory=_lazy_panel("kexp.util.guis.interlock.interlock_panel", "InterlockPanel"),
        server_cmd=[_PY, "-m", "kexp.util.guis.interlock.interlock_server"],
        cwd=_REPO,
        com_label=INTERLOCK_COM,
        graceful_stop_timeout_s=10.0,
        restart_on_crash=False,
        default_dock_area="top",
        default_placement="dock",
    ),
]


def get_spec(server_id: str) -> Optional[ServerSpec]:
    for s in SERVER_SPECS:
        if s.id == server_id:
            return s
    return None


__all__ = ["SERVER_SPECS", "get_spec"]
