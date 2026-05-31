"""Bristol wavemeter panel - embeds the waxx client GUI.

The dashboard always uses the *client* view; the headless server runs as
a separate subprocess managed by the supervisor.  This keeps the panel
identical whether the dashboard is on the server host or a remote host.
"""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


class BristolServerPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.bristol.bristol_wavemeter_client_gui import BristolClientWindow  # noqa: PLC0415

        self._gui = BristolClientWindow()
        embed_main_window(self, self._gui)


# Alias for clarity from the client dashboard.
BristolClientPanel = BristolServerPanel


__all__ = ["BristolServerPanel", "BristolClientPanel"]
