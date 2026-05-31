"""Basler cameras panel - embeds the waxx BaslerCamerasMainWindow.

This main window already provides discovery + per-camera docks; we just
embed it.  Because it uses nested QDockWidgets internally, the dashboard
hosts it as a regular embedded widget (the inner docks remain functional).
"""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


class BaslerServerPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.basler.basler_cameras_gui import BaslerCamerasMainWindow  # noqa: PLC0415

        self._gui = BaslerCamerasMainWindow(auto_open=False)
        # Basler hosts nested QDockWidgets inside its QMainWindow; embed
        # the whole QMainWindow visibly so those docks remain reachable.
        embed_main_window(self, self._gui, embed_as_window=True)


# Same widget works on either dashboard side.
BaslerClientPanel = BaslerServerPanel


__all__ = ["BaslerServerPanel", "BaslerClientPanel"]
