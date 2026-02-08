"""kexp-specific entry point for the LiveOD viewer client.

All implementation lives in ``waxx.util.live_od.gui.viewer_window``.
This wrapper only supplies the default server IP/port from ``kexp.config.ip``.

Usage::

    python -m kexp.util.live_od.gui.viewer_window
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from waxx.util.live_od.gui.viewer_window import (   # noqa: F401 — re-export
    LiveODClientWindow as _LiveODClientWindow,
    ConnectionIndicator,
    XVarDisplay,
)
from kexp.config.ip import CAMERA_SERVER_IP, CAMERA_SERVER_PORT

class LiveODClientWindow(_LiveODClientWindow):
    """LiveOD viewer client with kexp default server address."""

    def __init__(self, server_ip=None, server_port=None):
        super().__init__(
            server_ip=server_ip or CAMERA_SERVER_IP,
            server_port=server_port or CAMERA_SERVER_PORT,
        )

def main():
    app = QApplication(sys.argv)
    win = LiveODClientWindow()
    win.setWindowTitle("LiveOD Viewer (Client)")
    win.resize(1400, 900)
    try:
        win.setWindowIcon(QIcon("banana-icon.png"))
    except Exception:
        pass
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
