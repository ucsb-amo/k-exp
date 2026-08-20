"""Client registry: declares every panel that the client dashboard shows.

Client panels are non-server tools (ethernet relay, remote control, etc.)
plus *client-side* views of the headless servers running on the lab PC
(ALS, Precilaser, Bristol wavemeter, Basler cameras, magnetometer,
interlock).  All panels are listed so the user can show/hide them from
the Panels menu; ``default_visible=False`` means the panel exists but is
hidden on first launch.

Imports are lazy for the same reason as :mod:`server_registry`.
"""

from __future__ import annotations

from typing import Optional

from waxx.util.dashboard.panel_spec import ClientSpec


def _lazy_panel(module_path: str, attr: str):
    def factory():
        import importlib  # noqa: PLC0415
        mod = importlib.import_module(module_path)
        cls = getattr(mod, attr)
        return cls()
    return factory


CLIENT_SPECS: list[ClientSpec] = [
    # --- core control / status (always visible) -----------------------
    ClientSpec(
        id="device_control",
        label="Device Control",
        icon="🎮",  # matches device_control_gui window icon
        body_factory=_lazy_panel("kexp.util.guis.device_state_gui.monitor_panel", "MonitorClientPanel"),
        default_dock_area="bottom",
        default_placement="dock",
        default_visible=True,
    ),
    ClientSpec(
        id="ethernet_relay",
        label="Ethernet Relay",
        icon="🔌",
        body_factory=_lazy_panel("kexp.util.guis.ethernet_relay.ethernet_relay_panel", "EthernetRelayPanel"),
        default_dock_area="right",
        default_placement="tab",
        tab_group="control",
        default_visible=True,
    ),
    ClientSpec(
        id="remote_control",
        label="Remote Control",
        icon="📡",  # matches remote_control_gui window icon
        body_factory=_lazy_panel("kexp.util.guis.remote_control_panel", "RemoteControlPanel"),
        default_dock_area="right",
        default_placement="tab",
        tab_group="control",
        default_visible=True,
    ),
    ClientSpec(
        id="keysight",
        label="Keysight",
        icon="🍌",
        body_factory=_lazy_panel("kexp.util.guis.keysight_monitor.keysight_panel", "KeysightPanel"),
        default_dock_area="right",
        default_placement="tab",
        tab_group="control",
        default_visible=True,
    ),
    ClientSpec(
        id="tpi",
        label="TPI Signal Generators",
        icon="📻",
        body_factory=_lazy_panel("waxx.util.guis.tpi.tpi_panel", "TpiClientPanel"),
        default_dock_area="right",
        default_placement="tab",
        tab_group="control",
        default_visible=True,
    ),

    # --- remote views of the lab servers ------------------------------
    ClientSpec(
        id="bristol",
        label="Bristol Wavemeter",
        icon="〰",
        body_factory=_lazy_panel(
            "kexp.util.guis.wavemeter_monitor.bristol.bristol_panel",
            "BristolClientPanel",
        ),
        default_dock_area="right",
        default_placement="dock",
        default_visible=True,
    ),
    ClientSpec(
        id="basler",
        label="Basler Cameras",
        icon="📷",
        body_factory=_lazy_panel("kexp.util.guis.basler.basler_panel", "BaslerClientPanel"),
        default_dock_area="right",
        default_placement="dock",
        default_visible=True,
    ),
    ClientSpec(
        id="als",
        label="ALS Laser",
        icon="🔫",
        body_factory=_lazy_panel("kexp.util.guis.lasers.als.als_panel", "AlsPanel"),
        default_dock_area="left",
        default_placement="dock",
        default_visible=False,
    ),
    ClientSpec(
        id="precilaser",
        label="Precilaser",
        icon="💀",
        body_factory=_lazy_panel(
            "kexp.util.guis.lasers.precilaser.precilaser_panel",
            "PrecilaserPanel",
        ),
        default_dock_area="left",
        default_placement="dock",
        default_visible=False,
    ),
    ClientSpec(
        id="magnetometer",
        label="HMR Magnetometer",
        icon="🧲",
        body_factory=_lazy_panel(
            "kexp.util.guis.magnetic_field_monitor.magnetometer_panel",
            "MagnetometerPanel",
        ),
        default_dock_area="left",
        default_placement="dock",
        default_visible=False,
    ),
    ClientSpec(
        id="interlock",
        label="Interlock (read-only view)",
        icon="🔒",
        body_factory=_lazy_panel("kexp.util.guis.interlock.interlock_panel", "InterlockClientPanel"),
        default_dock_area="top",
        default_placement="dock",
        default_visible=False,
    ),
]


def get_spec(client_id: str) -> Optional[ClientSpec]:
    for s in CLIENT_SPECS:
        if s.id == client_id:
            return s
    return None


__all__ = ["CLIENT_SPECS", "get_spec"]



def get_spec(client_id: str) -> Optional[ClientSpec]:
    for s in CLIENT_SPECS:
        if s.id == client_id:
            return s
    return None


__all__ = ["CLIENT_SPECS", "get_spec"]
