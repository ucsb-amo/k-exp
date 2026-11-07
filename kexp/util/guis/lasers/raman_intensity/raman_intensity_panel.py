"""Dashboard panel for the Raman intensity PID (waxx IntensityPIDPanel with this
machine's id and loop names).

Standalone window (the server must be running):

    python -m kexp.util.guis.lasers.raman_intensity.raman_intensity_panel
"""

from __future__ import annotations

from kexp.util.guis.lasers.raman_intensity import LOOP_NAMES, SERVER_ID, TITLE
from waxx.util.guis.intensity_pid.intensity_pid_panel import IntensityPIDPanel


class RamanIntensityPanel(IntensityPIDPanel):
    def __init__(self, parent=None):
        super().__init__(SERVER_ID, title=TITLE, loop_names=LOOP_NAMES, parent=parent)


def main() -> int:
    import sys  # noqa: PLC0415

    from PyQt6.QtWidgets import QApplication  # noqa: PLC0415

    app = QApplication.instance() or QApplication(sys.argv)
    window = RamanIntensityPanel()
    window.setWindowTitle(TITLE)
    window.resize(460, 360)
    window.show()
    code = app.exec()
    window.cleanup()
    return code


__all__ = ["RamanIntensityPanel"]

if __name__ == "__main__":
    raise SystemExit(main())
