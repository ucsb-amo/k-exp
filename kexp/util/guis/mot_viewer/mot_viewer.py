import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QFont, QIcon
from PyQt6.QtCore import Qt

from beacon.camera.viewer.main_window import CameraViewerMainWindow

mot_basler_serial = "40277706"


def make_viewer(window_cls=CameraViewerMainWindow):
    """The MOT camera's viewer window, with its own saved layout."""
    viewer = window_cls(
        serial_filter=[mot_basler_serial],
        auto_open=True,
        layout_key="mot_viewer",
    )
    viewer.setWindowTitle("MOT Viewer")
    return viewer


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

    viewer = make_viewer()
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
