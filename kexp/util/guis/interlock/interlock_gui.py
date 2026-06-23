"""interlock_gui.py — standalone wrapper kept for backward compatibility.

Spawns the headless :mod:`interlock_server` as a child Python process,
then opens a single-window UI containing the same :class:`InterlockPanel`
the dashboard uses.  The panel discovers the just-spawned server over the
LAN beacon and talks to it via TCP — same code path as the dashboard.

When this window closes, the child server is asked to shut down (and
killed after a graceful-stop timeout, never orphaned).

Why a child process and not in-thread?
--------------------------------------
The interlock service uses a Windows named mutex (IT3) to prevent two
instances.  Running it in-process here would conflict with the dashboard
also wanting to spawn it.  Using a subprocess keeps behavior identical
in both standalone and dashboard cases, and means the GUI window can
crash without taking down safety monitoring.
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox

from waxx.util.dashboard.logging_setup import configure_client_logging
from kexp.util.guis.interlock.interlock_panel import InterlockPanel


_LOG = logging.getLogger("kexp.dashboard.client.interlock.standalone")


class _InterlockStandaloneWindow(QMainWindow):
    """Window that spawns the server child process and embeds InterlockPanel."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interlock GUI (standalone)")
        self.resize(900, 600)

        self._panel = InterlockPanel(self)
        self.setCentralWidget(self._panel)

        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._proc.readyReadStandardOutput.connect(self._drain_stdout)
        self._proc.readyReadStandardError.connect(self._drain_stderr)
        self._proc.finished.connect(self._on_finished)

        QTimer.singleShot(0, self._start_server)

    def _start_server(self) -> None:
        program = sys.executable
        args = ["-m", "kexp.util.guis.interlock.interlock_server"]
        _LOG.info("Launching interlock server: %s %s", program, args)
        self._proc.start(program, args)
        if not self._proc.waitForStarted(3000):
            QMessageBox.critical(
                self,
                "Interlock server failed to start",
                "Could not spawn interlock_server.py.\n\n"
                "Check that the kexp environment is active and COM5 is free.",
            )

    def _drain_stdout(self) -> None:
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            _LOG.info("[server] %s", line)

    def _drain_stderr(self) -> None:
        data = bytes(self._proc.readAllStandardError()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            _LOG.warning("[server-err] %s", line)

    def _on_finished(self, exit_code: int, exit_status) -> None:
        _LOG.warning("Interlock server child exited code=%d status=%s",
                     exit_code, exit_status.name if hasattr(exit_status, "name") else exit_status)

    def closeEvent(self, ev):  # noqa: N802
        try:
            self._panel.cleanup()
        except Exception:
            _LOG.exception("Panel cleanup failed")
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            _LOG.info("Terminating interlock server child")
            try:
                self._proc.terminate()
                if not self._proc.waitForFinished(5000):
                    _LOG.warning("Graceful stop timed out; killing")
                    self._proc.kill()
                    self._proc.waitForFinished(2000)
            except Exception:
                _LOG.exception("Error stopping server child")
        super().closeEvent(ev)


def main() -> int:
    configure_client_logging()
    try:
        import ctypes  # noqa: PLC0415
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("weldlab.kexp.gui.interlock")
    except Exception:
        pass
    app = QApplication.instance() or QApplication(sys.argv)
    win = _InterlockStandaloneWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
