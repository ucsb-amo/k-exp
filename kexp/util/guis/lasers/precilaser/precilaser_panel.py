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
        # Lazily-measured collapse threshold for the Current panel.  Filled
        # by ``_measure_current_panel_min_h`` on first chance; falls back
        # to a small constant until then.
        self._current_panel_min_h: int = 110
        self._current_panel_min_h_measured: bool = False
        # Re-strip after deferred sizing in the embedded GUI settles, so
        # the dock can be collapsed below the GUI's natural sizeHint.
        QTimer.singleShot(0, lambda: _strip_minimum_sizes(self))
        QTimer.singleShot(100, lambda: _strip_minimum_sizes(self))
        QTimer.singleShot(150, self._measure_current_panel_min_h)
        QTimer.singleShot(150, self._apply_collapse_stages)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(0, 0)

    def resizeEvent(self, event):  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if not self._current_panel_min_h_measured:
            self._measure_current_panel_min_h()
        self._apply_collapse_stages()

    def _measure_current_panel_min_h(self) -> None:
        """Measure the natural minimum height of the current_panel groupbox.

        The default :data:`_COLLAPSE_STAGES` threshold for the current panel
        was hand-tuned and over-estimated the actual minimum, leaving
        whitespace below the readout label.  Measure the real
        ``minimumSizeHint`` with the edit widgets temporarily visible (so
        the threshold covers both expanded and collapsed editor states),
        cache it, and use it from :meth:`_apply_collapse_stages`.
        """
        cp = getattr(self._gui, "current_panel", None)
        if cp is None:
            self._current_panel_min_h_measured = True
            return
        try:
            inp = getattr(self._gui, "current_input", None)
            hint = getattr(self._gui, "current_submit_hint", None)
            prev_inp_vis = inp.isVisible() if inp is not None else None
            prev_hint_vis = hint.isVisible() if hint is not None else None
            if inp is not None:
                inp.setVisible(True)
            if hint is not None:
                hint.setVisible(True)
            layout = cp.layout()
            if layout is not None:
                layout.activate()
            measured = cp.minimumSizeHint().height()
            if inp is not None and prev_inp_vis is not None:
                inp.setVisible(prev_inp_vis)
            if hint is not None and prev_hint_vis is not None:
                hint.setVisible(prev_hint_vis)
            if measured > 0:
                # Small padding so the title bar of the groupbox isn't
                # clipped at the exact threshold.
                self._current_panel_min_h = int(measured) + 6
        except Exception:
            # Keep the fallback set in __init__.
            pass
        self._current_panel_min_h_measured = True

    def _apply_collapse_stages(self) -> None:
        h = self.height()
        for threshold, attrs in self._COLLAPSE_STAGES:
            if attrs == ("current_panel",):
                threshold = self._current_panel_min_h
            hide = h < threshold
            for attr in attrs:
                widget = getattr(self._gui, attr, None)
                if widget is not None:
                    widget.setVisible(not hide)


__all__ = ["PrecilaserPanel"]
