"""Monitor & device-state panels.

* :class:`MonitorPanel`        - server-side panel embedding ``MonitorServerGUI``
  (the small status widget run on the experiment PC).
* :class:`MonitorClientPanel`  - client-side panel embedding ``DeviceStateGUI``
  (the wide device-control window the lab actually interacts with).

Names follow the dashboard registries: server registry imports
``MonitorPanel``; client registry imports ``MonitorClientPanel``.
"""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


def _composite_kwargs(dds, dac) -> dict:
    """The Composite tab's definitions (kexp.config.composite_devices), its
    scenes, what their readbacks need, and the read-only telemetry
    (kexp...telemetry_providers).  A failure here costs the tab (or only the
    measured values), not the whole GUI."""
    import logging  # noqa: PLC0415
    log = logging.getLogger(__name__)
    try:
        from types import SimpleNamespace  # noqa: PLC0415
        from kexp.config.composite_devices import COMPOSITE_DEVICES, COMPOSITE_SCENES  # noqa: PLC0415
        from kexp.config.expt_params import ExptParams  # noqa: PLC0415
        kwargs = {"composite_devices": COMPOSITE_DEVICES,
                  "composite_scenes": COMPOSITE_SCENES,
                  "composite_params": ExptParams(),
                  "composite_frames": SimpleNamespace(dds=dds, dac=dac)}
    except Exception:
        log.exception("Composite device definitions failed to load; the Composite tab is off.")
        return {}
    try:
        from waxx.util.device_state.telemetry import TelemetryHub  # noqa: PLC0415
        from kexp.util.guis.device_state_gui.telemetry_providers import default_providers  # noqa: PLC0415
        kwargs["composite_telemetry"] = TelemetryHub(default_providers())
    except Exception:
        log.exception("Telemetry providers failed to load; the cards show no measured values.")
    return kwargs


class MonitorPanel(WidgetPanelBase):
    """Server-side monitor status panel (small)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QVBoxLayout  # noqa: PLC0415
        import os  # noqa: PLC0415
        from waxx.util.guis.monitor_server_gui import MonitorServerGUI  # noqa: PLC0415
        from kexp.config.ip import MONITOR_EXPT_PATH, MONITOR_STATE_FILEPATH, LOG_DIR  # noqa: PLC0415

        self._gui = MonitorServerGUI(monitor_expt_path=MONITOR_EXPT_PATH,
                                     config_file_path=MONITOR_STATE_FILEPATH,
                                     journal_dir=(os.path.join(LOG_DIR, "ops_journal")
                                                  if LOG_DIR else None))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._gui)


class MonitorClientPanel(WidgetPanelBase):
    """Client-side device-state control panel (wide)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.device_control_gui import DeviceStateGUI  # noqa: PLC0415
        # Avoid heavy ARTIQ hardware imports at module load time by deferring.
        # Instantiate the frames (both default to DummyCore — no hardware needed)
        # so that DDSWidget/DACWidget can look up default values via hasattr().
        try:
            from kexp.config.dac_id import dac_frame as _dac_frame_cls  # noqa: PLC0415
            from kexp.config.dds_id import dds_frame as _dds_frame_cls  # noqa: PLC0415
            dac = _dac_frame_cls()
            dds = _dds_frame_cls(dac_frame_obj=dac)
        except Exception:
            dds = None
            dac = None

        self._gui = DeviceStateGUI(
            dds_frame=dds,
            dac_frame=dac,
            **_composite_kwargs(dds, dac),
        )
        # Embedded directly (no scroll area), so the panel's minimum size is
        # the size that fits every channel card: the dock cannot be shrunk
        # to where cards would be clipped or squeezed.  The Composite tab
        # scrolls on its own inside the GUI.
        embed_main_window(self, self._gui)


__all__ = ["MonitorPanel", "MonitorClientPanel"]
