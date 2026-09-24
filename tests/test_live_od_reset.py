"""Reset responsiveness of liveOD, tested without a server, a socket or a camera.

Never start a real LiveODServer in a test: it beacons onto the lab network and a
live run could find it. The handler is driven through a stand-in object and the
client through scripted replies.
"""
import threading
import time
import types

import pytest

from kexp.util.live_od.live_od_server import LiveODServer
from kexp.util.live_od import live_od_client as lc
from waxa.base.scribe import Scribe

handle_wait = LiveODServer._handle_wait_cam_ready
NOT_YET = {"ok": False, "ready": False, "timed_out": True, "reset_requested": False,
           "error": "Camera ready timeout"}
OLD_SERVER_NOT_YET = {"ok": False, "ready": False, "error": "Camera ready timeout"}


def stand_in_server(reset=False, ready=False, grab_done=True):
    s = types.SimpleNamespace(_reset_requested=reset, _current_camera_key="xy_basler",
                              _basler_prev_grab_done_event=threading.Event(),
                              _cam_ready_event=threading.Event())
    if grab_done:
        s._basler_prev_grab_done_event.set()
    if ready:
        s._cam_ready_event.set()
    return s


def scripted_client(replies):
    c = lc.LiveODClient.__new__(lc.LiveODClient)     # no discovery, no socket
    c.last_reset_requested = False
    c.sent = []

    def _send_recv(payload, rcvtimeo_ms=None):
        c.sent.append(payload)
        reply = replies.pop(0)
        return reply() if callable(reply) else reply
    c._send_recv = _send_recv
    return c


@pytest.fixture(autouse=True)
def short_slices(monkeypatch):
    monkeypatch.setattr(lc, "CAM_READY_SLICE_S", 0.05)


# ---------------- server handler ----------------

def test_server_answers_a_pending_reset_at_once():
    t0 = time.time()
    reply = handle_wait(stand_in_server(reset=True), {"timeout": 5.0})
    assert reply == {"ok": True, "ready": False, "reset_requested": True}
    assert time.time() - t0 < 0.1


def test_server_reports_ready():
    reply = handle_wait(stand_in_server(ready=True), {"timeout": 0.2})
    assert reply["ok"] and reply["ready"] and reply["reset_requested"] is False


def test_server_marks_a_slice_timeout_as_not_ready_yet():
    reply = handle_wait(stand_in_server(), {"timeout": 0.1})
    assert not reply["ok"] and reply["timed_out"]
    reply = handle_wait(stand_in_server(grab_done=False), {"timeout": 0.1})
    assert reply["timed_out"] and "grab-loop" in reply["error"]


# ---------------- client ----------------

def test_client_asks_in_slices_until_ready():
    c = scripted_client([NOT_YET, NOT_YET, {"ok": True, "ready": True, "reset_requested": False}])
    assert c.wait_cam_ready(timeout=5.0) is True
    assert len(c.sent) == 3 and all(p["timeout"] == pytest.approx(0.05) for p in c.sent)


def test_client_returns_false_on_reset():
    c = scripted_client([NOT_YET, dict(NOT_YET, reset_requested=True)])
    assert c.wait_cam_ready(timeout=5.0) is False
    assert c.last_reset_requested is True


def test_client_works_against_a_server_without_the_new_keys():
    c = scripted_client([OLD_SERVER_NOT_YET, OLD_SERVER_NOT_YET, {"ok": True, "ready": True}])
    assert c.wait_cam_ready(timeout=5.0) is True


def test_client_raises_on_a_real_failure():
    c = scripted_client([{"ok": False, "error": "Unknown tag: WAIT_CAM_READY"}])
    with pytest.raises(ValueError, match="failed"):
        c.wait_cam_ready(timeout=5.0)


def test_client_timeout_keeps_the_servers_diagnosis():
    def slow():
        time.sleep(0.06)
        return dict(NOT_YET, error="Basler previous grab-loop exit timeout")
    c = scripted_client([slow] * 50)
    t0 = time.time()
    with pytest.raises(ValueError, match="grab-loop") as err:
        c.wait_cam_ready(timeout=0.2)
    assert "timed out" in str(err.value) and 0.2 <= time.time() - t0 < 1.0


def test_client_asks_once_even_with_no_time_left():
    c = scripted_client([{"ok": True, "ready": True}])
    assert c.wait_cam_ready(timeout=0.0) is True and len(c.sent) == 1


def test_client_caches_and_clears_the_reset_flag():
    c = scripted_client([{"ok": True, "reset_requested": True, "adjust_values": {}}])
    assert c.shot_complete(0, 2, {}) is True and c.last_reset_requested is True
    c = scripted_client([{"ok": True, "run_id": 1, "filepath": ""}])
    c.last_reset_requested = True
    c.init_run({})
    assert c.last_reset_requested is False


# ---------------- scribe (the experiment side) ----------------

class FakeClient:
    def __init__(self, cam_ready=True, poll=False, cached=False):
        self.cam_ready, self.poll, self.last_reset_requested = cam_ready, poll, cached
        self.polls, self.aborted = 0, False

    def wait_cam_ready(self, timeout):
        return self.cam_ready

    def poll_reset(self):
        self.polls += 1
        return self.poll

    def abort_run(self):
        self.aborted = True


class Expt(Scribe):
    def __init__(self, client, shots_done=0):
        self.live_od_client = client
        self._shot_complete_count = shots_done
        self.run_info = types.SimpleNamespace(run_id=123)


def test_a_reset_during_the_camera_wait_aborts_the_run():
    assert Expt(FakeClient(cam_ready=True)).wait_for_camera_ready(timeout=90.) is True
    e = Expt(FakeClient(cam_ready=False))
    with pytest.raises(RuntimeError, match="aborted"):
        e.wait_for_camera_ready(timeout=90.)
    assert e.live_od_client.aborted


def test_only_the_first_scan_iteration_polls():
    first = Expt(FakeClient(), shots_done=0)
    assert first._check_for_abort_signal() is False and first.live_od_client.polls == 1
    later = Expt(FakeClient(), shots_done=3)
    assert later._check_for_abort_signal() is False and later.live_od_client.polls == 0


def test_a_reset_before_the_first_shot_aborts():
    e = Expt(FakeClient(poll=True), shots_done=0)
    with pytest.raises(RuntimeError):
        e._check_for_abort_signal()
    assert e.live_od_client.aborted


def test_the_cached_flag_is_honoured_without_polling():
    e = Expt(FakeClient(cached=True), shots_done=3)
    with pytest.raises(RuntimeError):
        e._check_for_abort_signal()
    assert e.live_od_client.polls == 0
