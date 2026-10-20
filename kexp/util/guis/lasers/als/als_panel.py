"""ALS server panel - embeds the existing ALSControlGUI from waxx."""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from waxx.util.dashboard.embed_helpers import (
    StagedCollapsePanel,
    embed_main_window,
    _strip_minimum_sizes,
)


class AlsPanel(StagedCollapsePanel):
    """Embed ``waxx.util.guis.als.als_control_gui.ALSControlGUI``.

    Only this kexp wrapper knows the lab-specific IP / port / COM defaults;
    all UI logic lives in waxx.
    """

    # Vertical-collapse stages, first to hide first.  A stage hides below its
    # threshold (px), or sooner if what is left would not fit.  The Power and
    # Optical Output readouts are in no stage: they never hide, and their
    # height is the panel's minimum height.
    _COLLAPSE_STAGES = (
        # Hide telemetry + activity log dropdowns first.
        (270, ("telem_group", "log_box")),
        # Then the System panel — one ~20 px indicator row, and the same
        # states are readable from the power/optical readouts.
        (180, ("status_panel",)),
        # Last resort: the Controls box (Startup / Shutdown).  It is a
        # single button row now, so it survives much deeper collapse.
        (110, ("control_panel",)),
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
        self._start_staged_collapse()

    def _readout_modes(self) -> dict:
        g = self._gui
        return {
            g.power_box: [
                ([g.power_setpoint_label], [g.power_input_field, g.power_submit_hint]),
                ([g.power_input_field, g.power_submit_hint], [g.power_setpoint_label]),
            ],
        }


__all__ = ["AlsPanel"]
