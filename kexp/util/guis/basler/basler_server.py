"""kexp GUI launcher for BaslerCameraServer.

Opens a compact control window listing all cameras on this machine.
Each row has an Open / Close button.  The ZMQ server runs in a background
thread.  A "Log" button opens a popup text window on demand.

Usage::

    python basler_server.py              # instance 0 (normal)
    python basler_server.py --instance 1 # rare multi-instance case
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Qt log handler
# ---------------------------------------------------------------------------

class _QtLogHandler(logging.Handler):
    def __init__(self, callback) -> None:
        super().__init__()
        self._cb = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._cb(self.format(record))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Log popup window
# ---------------------------------------------------------------------------

class _LogWindow(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Server Log")
        self.resize(640, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        layout.addWidget(self._log)

    def append(self, text: str) -> None:
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(text + "\n")
        self._log.moveCursor(QTextCursor.MoveOperation.End)


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------

class _ServerThread(QThread):
    started_ok = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, instance_index: int, parent=None) -> None:
        super().__init__(parent)
        self.instance_index = instance_index
        self.server = None

    def run(self) -> None:
        try:
            from waxx.util.guis.basler.basler_camera_server import BaslerCameraServer
            self.server = BaslerCameraServer(instance_index=self.instance_index)
            self.started_ok.emit()
            self.server.start()
        except Exception as exc:
            self.error.emit(str(exc))

    def stop_server(self) -> None:
        if self.server is not None:
            self.server.stop()


# ---------------------------------------------------------------------------
# Per-camera row widget
# ---------------------------------------------------------------------------

class _CameraRow(QFrame):
    def __init__(self, mc, parent=None) -> None:
        super().__init__(parent)
        self.mc = mc
        self.setFrameShape(QFrame.Shape.StyledPanel)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 1, 6, 1)
        row.setSpacing(6)

        name = mc.user_id if mc.user_id else mc.serial
        row.addWidget(QLabel(f"<b>{name}</b>"), stretch=1)

        self._btn = QPushButton("Open")
        self._btn.setFixedWidth(60)
        self._btn.clicked.connect(self._toggle)
        row.addWidget(self._btn)

    def _toggle(self) -> None:
        self._btn.setEnabled(False)
        target = self.mc.close if self.mc.is_open else self.mc.open
        threading.Thread(target=self._run_toggle, args=(target,), daemon=True).start()

    def _run_toggle(self, fn) -> None:
        try:
            fn()
        except Exception as exc:
            logging.getLogger(__name__).error("Camera %s: %s", self.mc.serial, exc)
        QTimer.singleShot(0, self._refresh_ui)

    def refresh(self) -> None:
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        open_ = self.mc.is_open
        self._btn.setText("Close" if open_ else "Open")
        self._btn.setStyleSheet(
            "background:#1e4d2a;border-color:#3fad5a;color:#7fdd9a;" if open_ else ""
        )
        self._btn.setEnabled(True)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

_DARK = """
* { font-family: "Segoe UI", Arial, sans-serif; font-size: 11px; color: #d0d4e8; }
QMainWindow, QWidget, QDialog { background: #1a1b2e; }
QFrame[frameShape="1"] {
    background: #22233a; border: 1px solid #3a3c5a; border-radius: 4px;
}
QPushButton {
    background: #2d2f4a; border: 1px solid #4a4d72;
    border-radius: 4px; padding: 2px 8px; color: #c0c4de;
}
QPushButton:hover { background: #383a60; }
QPushButton:pressed { background: #22243e; }
QTextEdit { background: #12131f; border: 1px solid #2a2c44; }
QScrollArea { border: none; }
"""


class BaslerServerWindow(QMainWindow):
    def __init__(self, instance_index: int = 0) -> None:
        super().__init__()
        hostname = socket.gethostname()
        suffix = f":{instance_index}" if instance_index else ""
        self.setWindowTitle(f"Basler Server — {hostname}{suffix}")
        self.setStyleSheet(_DARK)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Camera rows (scrollable)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._cam_container = QWidget()
        self._cam_layout = QVBoxLayout(self._cam_container)
        self._cam_layout.setContentsMargins(0, 0, 0, 0)
        self._cam_layout.setSpacing(3)
        self._no_cam_lbl = QLabel("No cameras detected.")
        self._no_cam_lbl.setStyleSheet("color: #60638a;")
        self._cam_layout.addWidget(self._no_cam_lbl)
        self._cam_layout.addStretch()
        self._scroll.setWidget(self._cam_container)
        layout.addWidget(self._scroll, stretch=1)

        # Bottom bar: error label (hidden by default) + Log button
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 4, 0, 0)
        self._err_lbl = QLabel()
        self._err_lbl.setStyleSheet("color: #bf4040;")
        self._err_lbl.hide()
        bottom.addWidget(self._err_lbl, stretch=1)
        log_btn = QPushButton("Log…")
        log_btn.setFixedWidth(50)
        log_btn.clicked.connect(self._show_log)
        bottom.addWidget(log_btn)
        layout.addLayout(bottom)

        self._rows: dict[str, _CameraRow] = {}

        # Log popup (created once, shown on demand)
        self._log_window = _LogWindow(self)
        self._log_window.setStyleSheet(_DARK)

        # Log handler
        handler = _QtLogHandler(self._log_window.append)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S"
        ))
        logging.getLogger().addHandler(handler)

        # Server thread
        self._thread = _ServerThread(instance_index, self)
        self._thread.started_ok.connect(self._on_server_started)
        self._thread.error.connect(self._on_server_error)
        self._thread.start()

        # Poll timer
        self._poll = QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._refresh)
        self._poll.start()

        self.resize(300, 160)
        self.setMinimumWidth(240)
        self.setMinimumHeight(80)

    # ------------------------------------------------------------------ #

    def _show_log(self) -> None:
        self._log_window.show()
        self._log_window.raise_()

    def _on_server_started(self) -> None:
        self._rebuild_rows()

    def _on_server_error(self, msg: str) -> None:
        self._err_lbl.setText(msg)
        self._err_lbl.show()

    def _rebuild_rows(self) -> None:
        server = self._thread.server
        if server is None:
            return
        cameras = server._cameras
        if not cameras:
            self._no_cam_lbl.show()
            return
        self._no_cam_lbl.hide()
        for serial, mc in cameras.items():
            if serial not in self._rows:
                row = _CameraRow(mc)
                self._rows[serial] = row
                self._cam_layout.insertWidget(self._cam_layout.count() - 1, row)

    def _refresh(self) -> None:
        self._rebuild_rows()
        for row in self._rows.values():
            row.refresh()

    # ------------------------------------------------------------------ #

    def closeEvent(self, event) -> None:
        self._poll.stop()
        self._thread.stop_server()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Basler camera server (GUI)")
    parser.add_argument("--instance", type=int, default=0,
                        help="Instance index (0 for the normal single-server case)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    app = QApplication(sys.argv)

    pixmap = QPixmap(64, 64)
    from PyQt6.QtCore import Qt as _Qt
    pixmap.fill(_Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setFont(QFont("Segoe UI Emoji", 44))
    painter.drawText(pixmap.rect(), _Qt.AlignmentFlag.AlignCenter, "\U0001f6a8")
    painter.end()
    icon = QIcon(pixmap)
    app.setWindowIcon(icon)

    win = BaslerServerWindow(instance_index=args.instance)
    win.setWindowIcon(icon)
    win.show()

    # Dark title bar (Windows 10 1809+ / Windows 11)
    try:
        import ctypes
        hwnd = int(win.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

