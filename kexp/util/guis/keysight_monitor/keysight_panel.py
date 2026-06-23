"""Keysight monitor panel — embeds the *client* view.

The dashboard always uses the client widget; the headless ``KeysightServer``
runs as a separate subprocess managed by the supervisor.  This keeps the
panel identical on the server host and on remote clients, and ensures the
supplies are only ever talked to by one process (the server).
"""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout

from waxx.util.dashboard.embed_helpers import WidgetPanelBase


class KeysightPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.keysight.keysight_client_gui import KeysightClientWindow  # noqa: PLC0415

        self._gui = KeysightClientWindow()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._gui)


# Aliases for the server / client registries.  Both dashboards embed the
# same thin client widget — the only "talks to hardware" process is the
# headless KeysightServer launched by the server supervisor.
KeysightServerPanel = KeysightPanel
KeysightClientPanel = KeysightPanel


__all__ = ["KeysightPanel", "KeysightServerPanel", "KeysightClientPanel"]
