"""Precilaser server panel - embeds waxx PrecilaserControlGUI."""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


class PrecilaserPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.precilaser.precilaser_control_gui import PrecilaserControlGUI  # noqa: PLC0415

        # PrecilaserControlGUI takes no args today; if/when it grows config
        # parameters, plumb them through from kexp.config.ip here.
        self._gui = PrecilaserControlGUI()
        embed_main_window(self, self._gui, compact=True)


__all__ = ["PrecilaserPanel"]
