"""ALS server panel - embeds the existing ALSControlGUI from waxx."""

from __future__ import annotations

from PyQt6.QtCore import QSize, QTimer

from waxx.util.dashboard.embed_helpers import (
    WidgetPanelBase,
    embed_main_window,
    _strip_minimum_sizes,
)


class AlsPanel(WidgetPanelBase):
    """Embed ``waxx.util.guis.als.als_control_gui.ALSControlGUI``.

    Only this kexp wrapper knows the lab-specific IP / port / COM defaults;
    all UI logic lives in waxx.
    """

    # Vertical-collapse stages, in order: when the panel shrinks below the
    # corresponding threshold (px) we hide the listed attributes on the
    # embedded GUI.  Stages stack: at stage 0 nothing is hidden; at the
    # smallest height every stage's widgets are hidden.
    _COLLAPSE_STAGES = (
        # Hide telemetry + activity log dropdowns first.
        (480, ("telem_group", "log_box")),
        # Then hide the Controls box (startup / shutdown buttons).
        (320, ("control_panel",)),
        # Last resort: also hide the System (status indicators) panel.
        (220, ("status_panel",)),
    )

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
        self.setMinimumHeight(0)
        # ALSControlGUI re-applies a minimum height from its own
        # ``minimumSizeHint()`` after __init__ returns, and child widgets
        # (e.g. log_output, status indicators) hardcode ~80 px minimums.
        # Re-strip after the event loop ticks so the dock can be shrunk.
        QTimer.singleShot(0, lambda: _strip_minimum_sizes(self))
        QTimer.singleShot(100, lambda: _strip_minimum_sizes(self))
        # Apply collapse stages once so the panel honours the current
        # height even before the first resize event.
        QTimer.singleShot(150, self._apply_collapse_stages)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        # Override Qt's default (which sums child minimumSizeHints) so the
        # dashboard layout can collapse the panel to an arbitrarily small
        # height.
        return QSize(0, 0)

    def resizeEvent(self, event):  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._apply_collapse_stages()

    def _apply_collapse_stages(self) -> None:
        h = self.height()
        for threshold, attrs in self._COLLAPSE_STAGES:
            hide = h < threshold
            for attr in attrs:
                widget = getattr(self._gui, attr, None)
                if widget is not None:
                    widget.setVisible(not hide)


__all__ = ["AlsPanel"]
