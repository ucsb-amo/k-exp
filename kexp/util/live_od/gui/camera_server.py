#!/usr/bin/env python
"""
Start the LiveOD camera server with kexp defaults.

Usage::

    python -m kexp.util.live_od.gui.run_camera_server
"""

import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from waxx.util.live_od.gui.server_window import CameraServerWindow
from kexp.config.ip import CAMERA_SERVER_IP, CAMERA_SERVER_PORT


def main():
    app = QApplication(sys.argv)

    win = CameraServerWindow(
        host=CAMERA_SERVER_IP,
        port=CAMERA_SERVER_PORT
    )
    win.show()

    # Periodically give Python a chance to handle KeyboardInterrupt
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nShutting down...")
        win.server.stop()


if __name__ == "__main__":
    main()
