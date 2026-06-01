"""Precilaser server panel - embeds waxx PrecilaserControlGUI."""

from __future__ import annotations

from PyQt6.QtCore import QSize, QTimer

from waxx.util.dashboard.embed_helpers import (
    WidgetPanelBase,
    embed_main_window,
    _strip_minimum_sizes,
)


class PrecilaserPanel(WidgetPanelBase):
    # Vertical-collapse stages, smallest first.  When the panel shrinks
    # below each threshold (px) we hide the listed attributes on the
    # embedded GUI.  Stages stack.
    _COLLAPSE_STAGES = (
        # Hide Telemetry + Logs dropdowns first.
        (480, ("telem_wrap", "log_wrap")),
        # Then hide the Controls (startup/shutdown) box.
        (340, ("control_panel",)),
        # Then hide the Status Indicators panel.
        (260, ("status_panel",)),
        # Last to go: the Current readout/editor (most important to keep).
        (160, ("current_panel",)),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.precilaser.precilaser_control_gui import PrecilaserControlGUI  # noqa: PLC0415

        # PrecilaserControlGUI takes no args today; if/when it grows config
        # parameters, plumb them through from kexp.config.ip here.
        self._gui = PrecilaserControlGUI()
        embed_main_window(self, self._gui, compact=True)
        self.setMinimumHeight(0)
        # Re-strip after deferred sizing in the embedded GUI settles, so
        # the dock can be collapsed below the GUI's natural sizeHint.
        QTimer.singleShot(0, lambda: _strip_minimum_sizes(self))
        QTimer.singleShot(100, lambda: _strip_minimum_sizes(self))
        QTimer.singleShot(150, self._apply_collapse_stages)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
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


__all__ = ["PrecilaserPanel"]
