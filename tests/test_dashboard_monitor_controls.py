"""The server dashboard puts the monitor server's LED and Start / Stop /
Restart on the Device Control panel's header
(kexp.util.dashboard.server_dashboard_app).  Offscreen Qt; the supervisor is a
fake -- no process is started or killed."""
import os

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from waxx.util.dashboard.panel_container import ServerPanel
from waxx.util.dashboard.server_supervisor import SupervisorState
from kexp.util.dashboard import server_dashboard_app as app


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class FakeSupervisor(QObject):
    state_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.state = SupervisorState.RUNNING
        self.calls = []

    def start(self):
        self.calls.append("start")

    def reset_and_start(self):
        self.calls.append("reset_and_start")

    def stop(self):
        self.calls.append("stop")

    def restart(self):
        self.calls.append("restart")


@pytest.fixture
def wired(qapp, monkeypatch):
    answers = []

    def question(parent, title, text, *a, **k):
        answers.append(text)
        return app_answer[0]
    app_answer = [None]
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    panel = ServerPanel("device_control", "Device Control", None)
    sup = FakeSupervisor()
    app.wire_server_controls(panel, sup, "monitor")
    yield panel, sup, answers, app_answer, QMessageBox
    panel.deleteLater()


def test_device_control_carries_the_monitor_servers_controls():
    assert app.SERVER_CONTROLS_ON_CLIENT_PANEL == {"device_control": "monitor"}
    assert "device_control" in app.EXTRA_CLIENT_IDS_ON_SERVER_DASHBOARD


def test_the_header_follows_the_supervisor_and_asks_before_stop_and_restart(wired):
    panel, sup, answers, answer, box = wired
    header = panel.header()
    assert header._start_btn is not None and not header._start_btn.isEnabled()  # running
    assert header._stop_btn.isEnabled()
    sup.state_changed.emit(SupervisorState.IDLE)
    assert header._start_btn.isEnabled() and not header._stop_btn.isEnabled()
    header._start_btn.click()
    assert sup.calls == ["start"]
    sup.state_changed.emit(SupervisorState.RUNNING)
    answer[0] = box.StandardButton.No
    header._stop_btn.click()
    header._restart_btn.click()
    assert sup.calls == ["start"]                           # both declined
    assert "killed at once" in answers[0] and "does not start the monitor" in answers[1]
    answer[0] = box.StandardButton.Yes
    header._stop_btn.click()
    header._restart_btn.click()
    assert sup.calls == ["start", "stop", "restart"]
