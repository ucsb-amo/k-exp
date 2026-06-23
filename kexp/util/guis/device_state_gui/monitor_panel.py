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
        from kexp.config.ip import MONITOR_EXPT_PATH, MONITOR_STATE_FILEPATH  # noqa: PLC0415

        self._gui = MonitorServerGUI(monitor_expt_path=MONITOR_EXPT_PATH,
                                     config_file_path=MONITOR_STATE_FILEPATH)
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
        )
        from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget  # noqa: PLC0415
        from PyQt6.QtCore import Qt  # noqa: PLC0415
        container = QWidget()
        embed_main_window(container, self._gui)
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll)

    def resizeEvent(self, event):  # noqa: N802 (Qt API)
        # The embedded QMainWindow is hidden, so its own resize/show events
        # never fire.  Drive the responsive collapse from the panel instead;
        # the GUI measures the enclosing scroll viewport width itself.
        super().resizeEvent(event)
        gui = getattr(self, "_gui", None)
        if gui is not None:
            gui._recompute_compact()


__all__ = ["MonitorPanel", "MonitorClientPanel"]
