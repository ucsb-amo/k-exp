"""Keysight monitor panel - embeds the Keysight ``Window`` widget."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout

from waxx.util.dashboard.embed_helpers import WidgetPanelBase


class KeysightPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from kexp.util.guis.keysight_monitor.keysight_monitor_gui import Window  # noqa: PLC0415

        self._gui = Window()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._gui)


__all__ = ["KeysightPanel"]
