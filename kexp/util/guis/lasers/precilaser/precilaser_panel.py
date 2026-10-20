"""Precilaser server panel - embeds waxx PrecilaserControlGUI."""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from waxx.util.dashboard.embed_helpers import (
    StagedCollapsePanel,
    embed_main_window,
    _strip_minimum_sizes,
)


class PrecilaserPanel(StagedCollapsePanel):
    # Vertical-collapse stages, first to hide first.  A stage hides below its
    # threshold (px), or sooner if what is left would not fit.  The Current
    # readout is in no stage: it never hides, and its height is the panel's
    # minimum height.
    _COLLAPSE_STAGES = (
        # Hide Telemetry + Logs dropdowns first.
        (260, ("telem_wrap", "log_wrap")),
        # Then the Status panel — one ~20 px indicator row, and every
        # indicator state is also visible in Telemetry.
        (170, ("status_panel",)),
        # The Controls (Ramp On / Ramp Off) box survives well past that;
        # it is a single button row and the thing operators reach for.
        (110, ("control_panel",)),
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
        self._start_staged_collapse()

    def _readout_modes(self) -> dict:
        g = self._gui
        return {
            g.current_panel: [
                ([g.current_display_label], [g.current_input, g.current_submit_hint]),
                ([g.current_input, g.current_submit_hint], [g.current_display_label]),
            ],
        }


__all__ = ["PrecilaserPanel"]
