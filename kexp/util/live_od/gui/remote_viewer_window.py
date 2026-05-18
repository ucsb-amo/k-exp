"""
Standalone LiveOD remote viewer window.

Subscribes to the LiveOD Server's ZMQ PUB broadcast and displays
live OD images and shot progress without needing direct access to
the data drive or camera hardware.

Usage (run from any machine on the lab network)::

    python -m kexp.util.live_od.gui.remote_viewer_window
    python -m kexp.util.live_od.gui.remote_viewer_window 192.168.1.76
    python -m kexp.util.live_od.gui.remote_viewer_window 192.168.1.76 5561
"""

import pickle
import sys
import threading
from queue import Queue

import zmq
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from kexp.util.live_od.gui.plotter import LiveODPlotter
from kexp.util.live_od.gui.viewer import LiveODViewer


# ---------------------------------------------------------------------------
# ZMQ subscriber thread
# ---------------------------------------------------------------------------

class LiveODSubscriber(QThread):
    """Receives broadcast messages from ``LiveODBroadcaster`` and re-emits
    them as Qt signals so the GUI thread can process them safely."""

    od_image_signal = pyqtSignal(object)            # plot_data tuple
    shot_progress_signal = pyqtSignal(int, int, object)  # shot_idx, N_total, xvar_values
    run_started_signal = pyqtSignal(int)            # run_id
    run_done_signal = pyqtSignal()
    connection_status_signal = pyqtSignal(str)

    def __init__(self, ip: str, port: int):
        super().__init__()
        self._ip = ip
        self._port = port
        self._running = False

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, 500)        # 500 ms poll so stop() is noticed
        socket.setsockopt(zmq.SUBSCRIBE, b"")       # subscribe to all topics
        socket.connect(f"tcp://{self._ip}:{self._port}")
        self._running = True
        self.connection_status_signal.emit(
            f"Connected to tcp://{self._ip}:{self._port}"
        )
        try:
            while self._running:
                try:
                    raw = socket.recv()
                except zmq.Again:
                    continue  # poll timeout — check _running

                try:
                    msg = pickle.loads(raw)
                except Exception as exc:
                    print(f"[LiveODSubscriber] deserialisation error: {exc}")
                    continue

                tag = msg.get("tag", "")
                try:
                    if tag == "OD_IMAGE":
                        plot_data = (
                            msg["img_atoms"], msg["img_light"], msg["img_dark"],
                            msg["od"], msg["sum_od_x"], msg["sum_od_y"],
                        )
                        self.od_image_signal.emit(plot_data)
                    elif tag == "SHOT_PROGRESS":
                        self.shot_progress_signal.emit(
                            int(msg["shot_idx"]),
                            int(msg["N_total"]),
                            msg.get("xvar_values", {}),
                        )
                    elif tag == "RUN_STARTED":
                        self.run_started_signal.emit(int(msg.get("run_id", 0)))
                    elif tag == "RUN_DONE":
                        self.run_done_signal.emit()
                except Exception as exc:
                    print(f"[LiveODSubscriber] signal error ({tag}): {exc}")
        finally:
            socket.close()
            context.term()

    def stop(self):
        self._running = False


# ---------------------------------------------------------------------------
# Remote viewer window
# ---------------------------------------------------------------------------

class RemoteViewerWindow(QWidget):
    """Standalone window that subscribes to a LiveODBroadcaster and displays
    live OD images, sum-OD projections, and shot progress."""

    def __init__(self, ip: str = None, port: int = None):
        super().__init__()

        from kexp.config.ip import LIVEOD_SERVER_IP, LIVEOD_BROADCAST_PORT
        self._ip = ip if ip is not None else LIVEOD_SERVER_IP
        self._port = port if port is not None else LIVEOD_BROADCAST_PORT

        # Viewer + plotter (same components as the server window)
        self.plotting_queue: Queue = Queue()
        self.viewer_window = LiveODViewer()
        self.plotter = LiveODPlotter(self.viewer_window, self.plotting_queue)
        self.plotter.start()

        # Subscriber thread
        self.subscriber = LiveODSubscriber(self._ip, self._port)
        self.subscriber.od_image_signal.connect(self._on_od_image)
        self.subscriber.shot_progress_signal.connect(self._on_shot_progress)
        self.subscriber.run_started_signal.connect(self._on_run_started)
        self.subscriber.run_done_signal.connect(self._on_run_done)
        self.subscriber.connection_status_signal.connect(self._on_connection_status)
        self.subscriber.start()

        self._setup_layout()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _setup_layout(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Status bar
        status_bar = QHBoxLayout()
        self.status_label = QLabel(
            f"Connecting to tcp://{self._ip}:{self._port} …"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        self.status_label.setFont(font)
        status_bar.addWidget(self.status_label)

        self.reset_button = QPushButton("Reset")
        self.reset_button.setMinimumHeight(40)
        self.reset_button.setStyleSheet(
            'background-color: #ffcccc; font-size: 20px; font-weight: bold;'
        )
        self.reset_button.clicked.connect(self._on_reset_clicked)
        status_bar.addWidget(self.reset_button)

        layout.addLayout(status_bar)
        layout.addWidget(self.viewer_window)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_connection_status(self, msg: str):
        self.status_label.setText(msg)
        self.viewer_window.output_window.appendPlainText(msg)

    def _on_run_started(self, run_id: int):
        self.status_label.setText(
            f"Run {run_id} in progress  |  {self._ip}:{self._port}"
        )
        self.viewer_window.clear_plots()
        self.viewer_window.output_window.appendPlainText(
            f"--- Run {run_id} started ---"
        )

    def _on_shot_progress(self, shot_idx: int, N_total: int,
                          xvar_values: object):
        self.viewer_window.update_image_count(shot_idx + 1, N_total)
        # Minimal per-shot log: avoid flooding the text widget
        if (shot_idx + 1) % max(1, N_total // 20) == 0 or shot_idx == 0:
            self.viewer_window.output_window.appendPlainText(
                f"shot {shot_idx + 1}/{N_total}"
            )

    def _on_od_image(self, plot_data: tuple):
        self.plotting_queue.put(plot_data)

    def _on_run_done(self):
        self.viewer_window.output_window.appendPlainText("Run complete.")
        self.status_label.setText(
            f"Run complete  |  {self._ip}:{self._port}"
        )

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def _on_reset_clicked(self):
        self.viewer_window.output_window.appendPlainText("Sending Reset to server…")
        threading.Thread(target=self._send_reset_to_server, daemon=True).start()

    def _send_reset_to_server(self):
        from kexp.config.ip import LIVEOD_SERVER_PORT
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.SNDTIMEO, 3000)
        sock.setsockopt(zmq.RCVTIMEO, 3000)
        sock.connect(f"tcp://{self._ip}:{LIVEOD_SERVER_PORT}")
        try:
            sock.send(pickle.dumps({'tag': 'RESET'}))
            reply = pickle.loads(sock.recv())
            print(f"[RemoteViewer] Reset reply: {reply}")
        except Exception as exc:
            print(f"[RemoteViewer] Reset failed: {exc}")
        finally:
            sock.close()
            ctx.term()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self.subscriber.stop()
        self.subscriber.wait(2000)
        self.plotter.quit()
        self.plotter.wait(2000)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "weldlab.kexp.gui.live_od_viewer"
    )

    ip = sys.argv[1] if len(sys.argv) > 1 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 else None

    app = QApplication(sys.argv)
    win = RemoteViewerWindow(ip=ip, port=port)
    win.setWindowTitle("LiveOD Viewer")
    win.setWindowIcon(
        win.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
    )
    win.resize(1400, 900)
    win.show()
    sys.exit(app.exec())
