"""Dashboard panel for the Raman FP lock (waxx FPLockPanel with this machine's id).

Standalone window (no dashboard restart needed; the server must be running):

    python -m kexp.util.guis.lasers.raman_fp_lock.raman_fp_lock_panel
"""

from __future__ import annotations

from kexp.util.guis.lasers.raman_fp_lock import SERVER_ID
from waxx.util.guis.fp_lock.fp_lock_panel import FPLockPanel


class RamanFPLockPanel(FPLockPanel):
    def __init__(self, parent=None):
        super().__init__(SERVER_ID, title="Raman FP lock", parent=parent)


def main() -> int:
    import sys  # noqa: PLC0415

    from PyQt6.QtWidgets import QApplication  # noqa: PLC0415

    app = QApplication.instance() or QApplication(sys.argv)
    window = RamanFPLockPanel()
    window.setWindowTitle("Raman FP lock")
    window.resize(720, 900)
    window.show()
    code = app.exec()
    window.cleanup()
    return code


__all__ = ["RamanFPLockPanel"]

if __name__ == "__main__":
    raise SystemExit(main())
