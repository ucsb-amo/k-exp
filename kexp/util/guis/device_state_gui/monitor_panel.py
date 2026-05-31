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


class MonitorPanel(WidgetPanelBase):
    """Server-side monitor status panel (small)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QVBoxLayout  # noqa: PLC0415
        from waxx.util.guis.monitor_server_gui import MonitorServerGUI  # noqa: PLC0415
        from kexp.config.ip import MONITOR_EXPT_PATH  # noqa: PLC0415

        self._gui = MonitorServerGUI(monitor_expt_path=MONITOR_EXPT_PATH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._gui)


class MonitorClientPanel(WidgetPanelBase):
    """Client-side device-state control panel (wide)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.device_control_gui import DeviceStateGUI  # noqa: PLC0415
        from kexp.config.ip import (  # noqa: PLC0415
            MONITOR_STATE_FILEPATH,
            server_talk,
        )
        # Avoid heavy ARTIQ hardware imports at module load time by deferring.
        try:
            from kexp.config import dds_frame as _dds_frame_mod  # noqa: PLC0415
            from kexp.config import dac_frame as _dac_frame_mod  # noqa: PLC0415
            dds_frame = getattr(_dds_frame_mod, "dds_frame", None)
            dac_frame = getattr(_dac_frame_mod, "dac_frame", None)
        except Exception:
            dds_frame = None
            dac_frame = None

        self._gui = DeviceStateGUI(
            device_state_json_path=MONITOR_STATE_FILEPATH,
            server_talk=server_talk,
            dds_frame=dds_frame,
            dac_frame=dac_frame,
        )
        embed_main_window(self, self._gui)


__all__ = ["MonitorPanel", "MonitorClientPanel"]
