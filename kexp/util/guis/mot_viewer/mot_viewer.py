import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QFont, QIcon
from PyQt6.QtCore import Qt

from waxx.util.guis.basler.basler_cameras_gui import BaslerCamerasMainWindow

mot_basler_serial = "40277706"

def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('kexp.mot_viewer')
    except Exception:
        pass

    app = QApplication(sys.argv)

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setFont(QFont("Segoe UI Emoji", 48))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "\U0001f534")
    painter.end()
    app.setWindowIcon(QIcon(pixmap))

    viewer = BaslerCamerasMainWindow(
        serial_filter=[mot_basler_serial],
        auto_open=True,
    )
    viewer.setWindowTitle("MOT Viewer")
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
