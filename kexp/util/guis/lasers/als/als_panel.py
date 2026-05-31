"""ALS server panel - embeds the existing ALSControlGUI from waxx."""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


class AlsPanel(WidgetPanelBase):
    """Embed ``waxx.util.guis.als.als_control_gui.ALSControlGUI``.

    Only this kexp wrapper knows the lab-specific IP / port / COM defaults;
    all UI logic lives in waxx.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.als.als_control_gui import ALSControlGUI  # noqa: PLC0415
        from kexp.config.ip import ALS_COM, SRS_CONTROL_IP  # noqa: PLC0415

        self._gui = ALSControlGUI(
            ip=SRS_CONTROL_IP,
            port=5557,
            serial_port=ALS_COM,
        )
        embed_main_window(self, self._gui, compact=True)


__all__ = ["AlsPanel"]
