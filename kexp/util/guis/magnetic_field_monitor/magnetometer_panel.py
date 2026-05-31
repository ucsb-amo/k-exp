"""HMR Magnetometer server panel - embeds waxx MagnetometerGUI."""

from __future__ import annotations

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, embed_main_window


class MagnetometerPanel(WidgetPanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_gui import MagnetometerGUI  # noqa: PLC0415
        from kexp.config.ip import MAGNETOMETER_REFERENCE_CSV_PATH  # noqa: PLC0415

        self._gui = MagnetometerGUI(reference_csv_path=MAGNETOMETER_REFERENCE_CSV_PATH)
        embed_main_window(self, self._gui, compact=True)


__all__ = ["MagnetometerPanel"]
