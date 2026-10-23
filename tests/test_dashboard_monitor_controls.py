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
    assert "Monitor panel's Monitor tab" in answers[1]
    answer[0] = box.StandardButton.Yes
    header._stop_btn.click()
    header._restart_btn.click()
    assert sup.calls == ["start", "stop", "restart"]


# --- the monitor server's own panel (run queue + state, over the network) ------------------

def test_the_monitor_entry_has_a_panel_and_keeps_its_id():
    from kexp.util.dashboard.server_registry import SERVER_SPECS
    spec = next(s for s in SERVER_SPECS if s.id == "monitor")    # QSettings dock keys
    assert not spec.hidden_panel and spec.body_factory is not None
    assert spec.server_cmd and spec.server_cmd[-1].endswith("monitor_server_headless")


def test_monitor_panel_hosts_the_network_panel_and_cleans_it_up(qapp):
    from waxx.util.guis import monitor_panel as wmp
    from kexp.util.guis.device_state_gui.monitor_panel import MonitorPanel

    made = []

    class Client:
        def request(self, obj, timeout=5.0, attempts=2):
            return {"status": "ok", "jobs": [], "next": [], "run_queue": {"state": "idle"}}

        def get_status(self):
            return None

        def send_message(self, text, timeout=5.0, attempts=2):
            return None

    def factory(discovery_timeout):
        made.append(Client())
        return made[-1]

    panel = MonitorPanel(panel_factory=lambda: wmp.MonitorServerPanel(
        link=wmp.MonitorLink(factory), listener_factory=None, synchronous=True))
    inner = panel._panel
    assert inner.isAncestorOf(inner.state_panel) and inner.isAncestorOf(inner.queue_panel)
    assert made == []                                    # no discovery until a request
    panel.cleanup()
    assert not inner.timer.isActive()
    panel.deleteLater()


def test_monitor_panel_offers_start_live_od_from_kexps_bat(qapp, monkeypatch):
    """2026-10-21: the Monitor panel's Start liveOD runs kexp/_bat/live_od.bat
    (passed in from kexp; waxx knows no path).  Nothing is pressed, the real
    launcher is replaced by a failure, the beacon probe by a fake (the real
    registry would bind UDP 50099), QSettings by None (the registry)."""
    import os
    from waxx.util.guis import live_od_launch as lol
    from waxx.util.guis import run_queue_panel as rqp
    from kexp.util.guis.device_state_gui import monitor_panel as kmp

    monkeypatch.setattr(rqp, "panel_settings", lambda: None)
    monkeypatch.setattr(lol, "beacon_probe", lambda: ("absent", "no liveOD beacon (test)"))
    monkeypatch.setattr(lol, "start_bat", lambda *a, **k: pytest.fail("the real launcher ran"))
    monkeypatch.setattr(kmp, "live_od_host_refusal", lambda resolve=None: (lambda: ""))
    panel = kmp.MonitorPanel()
    try:
        button = panel._panel.state_panel.live_od_button
        assert button is not None and button.isEnabled()
        assert button.bat == kmp.live_od_bat() and os.path.isfile(button.bat)
        assert button.bat.replace("\\", "/").endswith("kexp/_bat/live_od.bat")
    finally:
        panel.cleanup()
        panel.deleteLater()


def test_start_live_od_refuses_any_pc_but_kong():
    from kexp.util.guis.device_state_gui import monitor_panel as kmp
    asked = []

    def resolve():
        asked.append(1)
        return "192.168.1.9"
    refusal = kmp.live_od_host_refusal(resolve)
    assert "kong (192.168.1.76)" in refusal() and "192.168.1.9" in refusal()
    assert asked == [1]                                   # looked up once
    assert kmp.live_od_host_refusal(lambda: kmp.LIVE_OD_HOST_IP)() == ""
    assert "not on the lab subnet" in kmp.live_od_host_refusal(lambda: None)()
