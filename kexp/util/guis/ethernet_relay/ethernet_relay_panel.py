"""Ethernet Relay panel - embeds EthernetRelayGUI."""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


class EthernetRelayPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from kexp.util.guis.ethernet_relay.ethernet_relay_gui import EthernetRelayGUI  # noqa: PLC0415

        self._gui = EthernetRelayGUI()
        embed_main_window(self, self._gui)


__all__ = ["EthernetRelayPanel"]
