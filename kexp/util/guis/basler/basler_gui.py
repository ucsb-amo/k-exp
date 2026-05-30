"""kexp launcher for the unified Basler cameras GUI.

Opens a window showing all Basler cameras found across the lab network.
Cameras start in the closed state; use the "Open Camera" button per dock.

Usage::

    python basler_gui.py
"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtCore import Qt

from waxx.util.guis.basler.basler_cameras_gui import BaslerCamerasMainWindow


def _camera_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setFont(QFont("Segoe UI Emoji", 44))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "\U0001f4f7")
    painter.end()
    return QIcon(pixmap)


def main() -> None:
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('kexp.basler_gui')
    except Exception:
        pass

    app = QApplication(sys.argv)
    icon = _camera_icon()
    app.setWindowIcon(icon)

    win = BaslerCamerasMainWindow(auto_open=False)
    win.setWindowIcon(icon)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
