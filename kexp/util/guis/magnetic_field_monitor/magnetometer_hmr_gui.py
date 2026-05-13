import sys

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_gui import MagnetometerGUI
from kexp.config.ip import (
    MAGNETOMETER_REFERENCE_CSV_PATH,
    MAGNETOMETER_SERVER_IP,
    MAGNETOMETER_SERVER_PORT,
)


def _create_magnet_icon():
    icon = QtGui.QIcon()

    for size in (16, 24, 32, 48, 64, 128):
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        font = QtGui.QFont()
        font.setPixelSize(max(12, int(size * 0.8)))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "🧲")

        painter.end()
        icon.addPixmap(pixmap)

    return icon

def main():
    app = QtWidgets.QApplication(sys.argv)
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    icon = _create_magnet_icon()
    app.setWindowIcon(icon)

    window = MagnetometerGUI(server_host=MAGNETOMETER_SERVER_IP,
                              server_port=MAGNETOMETER_SERVER_PORT,
                              reference_csv_path=MAGNETOMETER_REFERENCE_CSV_PATH)
    window.setWindowIcon(icon)
    window.show()

    try:
        return app.exec()
    except Exception:
        window.shutdown()
        raise

if __name__ == "__main__":
    sys.exit(main())