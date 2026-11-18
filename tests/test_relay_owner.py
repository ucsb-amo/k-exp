"""The ethernet relay's one owner: the board driver against a fake NCD board on
localhost, the kill-first lock, RelayOwner (bounded contacts, cache, ARTIQ
restart jobs that restore power), and the client EthernetRelay's fallbacks.

Nothing touches the real relay or the network beyond 127.0.0.1; no beacon,
no discovery (the client is handed a fake interlock client).
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from kexp.control import ethernet_relay as er
from kexp.util.guis.interlock.relay_owner import PriorityLock, RelayOwner


def _until(pred, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


# ---------------------------------------------------------------------------
# A fake NCD board (ProXR API over TCP: 170, len, payload..., checksum)
# ---------------------------------------------------------------------------

class FakeBoard:
    def __init__(self):
        self.states = [False, False, False, False]
        self.mode = "ok"          # ok | short | silent
        self.commands = []
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(4)
        self._sock.settimeout(0.1)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @staticmethod
    def _wrap(payload):
        pkt = [170, len(payload)] + list(payload)
        return bytes(pkt + [sum(pkt) & 255])

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                conn.settimeout(2.0)
                try:
                    self._handle(conn)
                except OSError:
                    pass

    def _handle(self, conn):
        while not self._stop.is_set():
            head = conn.recv(2)
            if len(head) < 2:
                return
            n = head[1]
            rest = b""
            while len(rest) < n + 1:
                chunk = conn.recv(n + 1 - len(rest))
                if not chunk:
                    return
                rest += chunk
            payload = rest[:n]
            self.commands.append(list(payload))
            if self.mode == "silent":
                continue
            cmd, idx = payload[1], payload[2] + 1 if len(payload) > 2 else None
            if cmd == 48:
                self.states[idx - 1] = True
                reply = self._wrap([85])
            elif cmd == 47:
                self.states[idx - 1] = False
                reply = self._wrap([85])
            elif cmd == 44:
                reply = self._wrap([1 if self.states[idx - 1] else 0])
            else:
                reply = self._wrap([0])
            if self.mode == "short":
                reply = reply[:2]
            conn.sendall(reply)

    def close(self):
        self._stop.set()
        self._sock.close()


@pytest.fixture
def board():
    b = FakeBoard()
    yield b
    b.close()


def _direct(board):
    return er.EthernetRelayDirect(relay_ip="127.0.0.1", port=board.port)


# ---------------------------------------------------------------------------
# The board driver
# ---------------------------------------------------------------------------

def test_direct_reads_and_writes_in_one_contact(board):
    d = _direct(board)
    board.states = [False, True, False, True]
    assert d.read_relay_status(retries=0, timeout=1.0) == [False, True, False, True]
    assert d.set_channel_and_read_all(er.SOURCE_RELAY_IDX, True, retries=0, timeout=1.0) \
        == [False, True, True, True]
    assert d.kill_magnets_and_read(retries=0, timeout=1.0) is False
    assert board.states == [False, False, True, True]
    assert d.board is None                          # closed after each contact


def test_a_short_reply_is_an_error_not_a_partial_packet(board):
    board.mode = "short"
    with pytest.raises((ConnectionError, socket.timeout, TimeoutError)):
        _direct(board).read_relay_status(retries=0, timeout=0.5)


def test_one_contact_never_outlasts_its_budget(board):
    board.mode = "silent"                           # accepts, never answers
    t0 = time.monotonic()
    with pytest.raises((socket.timeout, TimeoutError)):
        _direct(board).read_relay_status(retries=0, timeout=0.4)   # four reads
    assert time.monotonic() - t0 < 0.8


def test_old_relay_methods_still_work_on_the_direct_class(board):
    d = _direct(board)
    d.source_on(retries=0, timeout=1.0)
    assert d.read_source_status(retries=0, timeout=1.0) is True
    d.source_off(retries=0, timeout=1.0)
    assert board.states[er.SOURCE_RELAY_IDX - 1] is False


# ---------------------------------------------------------------------------
# Kill-first lock
# ---------------------------------------------------------------------------

def test_a_waiting_kill_goes_before_a_waiting_write():
    lock = PriorityLock()
    order = []
    assert lock.acquire()

    def take(name, priority):
        assert lock.acquire(priority=priority, timeout=5)
        order.append(name)
        time.sleep(0.02)
        lock.release()

    normal = threading.Thread(target=take, args=("write", False))
    normal.start()
    time.sleep(0.05)                                 # the write waits first
    kill = threading.Thread(target=take, args=("kill", True))
    kill.start()
    time.sleep(0.05)
    lock.release()
    normal.join(2)
    kill.join(2)
    assert order == ["kill", "write"]


def test_a_write_times_out_while_a_kill_waits():
    lock = PriorityLock()
    assert lock.acquire()
    t = threading.Thread(target=lambda: (lock.acquire(priority=True), lock.release()))
    t.start()
    time.sleep(0.05)
    assert lock.acquire(timeout=0.1) is False
    lock.release()
    t.join(2)


# ---------------------------------------------------------------------------
# RelayOwner
# ---------------------------------------------------------------------------

class FakeDriver:
    def __init__(self):
        self.states = [False, True, False, False]
        self.writes = []
        self.down = False
        self.hold_s = 0.0

    def _contact(self):
        if self.down:
            raise ConnectionRefusedError(10061, "refused (fake)")
        if self.hold_s:
            time.sleep(self.hold_s)

    def read_relay_status(self, retries=None, timeout=None):
        self._contact()
        return list(self.states)

    def read_magnet_status(self, retries=None, timeout=None):
        self._contact()
        return self.states[1]

    def kill_magnets_and_read(self, retries=None, timeout=None):
        self._contact()
        self.writes.append((2, False))
        self.states[1] = False
        return False

    def set_channel_and_read_all(self, idx, on, retries=None, timeout=None):
        self._contact()
        self.writes.append((idx, bool(on)))
        self.states[idx - 1] = bool(on)
        return list(self.states)

    def set_channels_and_read_all(self, states, retries=None, timeout=None):
        self._contact()
        for idx, on in states.items():
            self.writes.append((idx, bool(on)))
            self.states[idx - 1] = bool(on)
        return list(self.states)


def test_owner_refuses_to_be_built_on_the_client():
    with pytest.raises(TypeError):
        RelayOwner(er.EthernetRelay(client=object()))


def test_contacts_report_health_and_fill_the_cache():
    seen = []
    drv = FakeDriver()
    owner = RelayOwner(drv, on_contact=lambda ok, exc: seen.append(ok))
    assert owner.states is None and owner.magnets_enabled is None
    assert owner.read_all() == [False, True, False, False]
    drv.down = True
    with pytest.raises(ConnectionRefusedError):
        owner.read_all()
    assert seen == [True, False]
    assert owner.magnets_enabled is True             # last value read, with its age
    s = owner.stats()
    assert s["contacts"] == 2 and s["ok"] == 1 and s["refused"] == 1


def test_kill_until_off_keeps_trying_until_the_relay_answers():
    drv = FakeDriver()
    drv.down = True
    owner = RelayOwner(drv)
    assert owner.kill_until_off(0.2, gap_s=0.02) is False
    threading.Timer(0.2, lambda: setattr(drv, "down", False)).start()
    assert owner.kill_until_off(3.0, gap_s=0.02) is True
    assert drv.states[1] is False


def test_artiq_restart_all_cuts_satellites_then_main_and_restores_both():
    drv = FakeDriver()
    owner = RelayOwner(drv)
    reply = owner.start_artiq_restart("all", t_wait=0.05, t_between=0.05, requested_by="test")
    assert reply["status"] == "started"
    assert owner.start_artiq_restart("main", 0.05)["status"] == "busy"
    assert _until(lambda: owner.job(reply["job_id"])["state"] == "done")
    sat, main = er.ARTIQ_SATELLITES_RELAY_IDX, er.ARTIQ_MAIN_RELAY_IDX
    assert drv.writes == [(sat, True), (sat, False), (main, True), (main, False)]
    assert drv.states[sat - 1] is False and drv.states[main - 1] is False
    assert owner.job(reply["job_id"])["power_cut_now"] == []


def test_a_kill_does_not_wait_for_a_restart():
    drv = FakeDriver()
    owner = RelayOwner(drv)
    owner.start_artiq_restart("main", t_wait=2.0)
    assert _until(lambda: drv.states[er.ARTIQ_MAIN_RELAY_IDX - 1] is True)
    t0 = time.monotonic()
    assert owner.kill_once() is False
    assert time.monotonic() - t0 < 0.2               # the job holds no lock while waiting
    owner.abort_job(timeout=2.0)


def test_an_aborted_restart_restores_crate_power():
    drv = FakeDriver()
    owner = RelayOwner(drv)
    job_id = owner.start_artiq_restart("satellites", t_wait=30.0)["job_id"]
    sat = er.ARTIQ_SATELLITES_RELAY_IDX
    assert _until(lambda: drv.states[sat - 1] is True)
    owner.abort_job(timeout=2.0)
    job = owner.job(job_id)
    assert job["state"] == "aborted"
    assert drv.states[sat - 1] is False
    assert job["power_cut_now"] == []
    assert not owner.job_running


def test_a_restore_keeps_trying_while_the_relay_is_out():
    drv = FakeDriver()
    owner = RelayOwner(drv)
    job_id = owner.start_artiq_restart("main", t_wait=0.1)["job_id"]
    main = er.ARTIQ_MAIN_RELAY_IDX
    assert _until(lambda: drv.states[main - 1] is True)
    drv.down = True                                   # the relay stops answering mid-job
    time.sleep(0.4)
    assert owner.job(job_id)["state"] == "running"   # still trying to restore
    drv.down = False
    assert _until(lambda: owner.job(job_id)["state"] == "done", timeout=5.0)
    assert drv.states[main - 1] is False


def test_restart_arguments_are_checked():
    owner = RelayOwner(FakeDriver())
    assert owner.start_artiq_restart("everything", 1.0)["status"] == "error"
    assert owner.start_artiq_restart("main", 61.0)["status"] == "error"
    assert owner.start_artiq_restart("main", "3")["status"] == "started"
    owner.abort_job(timeout=2.0)


# ---------------------------------------------------------------------------
# The client EthernetRelay (fake interlock client; fake direct board)
# ---------------------------------------------------------------------------

class FakeInterlockClient:
    def __init__(self, replies=None, bare=None, fail=None):
        self.replies = replies or {}
        self.bare = bare or {}
        self.fail = fail
        self.sent = []

    def request(self, obj, timeout=None):
        self.sent.append(obj)
        if self.fail:
            raise self.fail
        reply = self.replies.get(obj["cmd"])
        return reply(obj) if callable(reply) else reply

    def send_command(self, command, timeout=None):
        self.sent.append(command)
        if self.fail:
            raise self.fail
        return self.bare[command]


class FakeDirect:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append(name)
            return [False, False, False, False]
        return call


OLD = {"status": "error", "message": "unknown command: {\"CMD\": ...}"}


def _client(**kw):
    direct = FakeDirect()
    relay = er.EthernetRelay(client=FakeInterlockClient(**kw), direct_factory=lambda: direct)
    relay.RETRY_GAP_S = 0.01
    return relay, direct


def test_client_sends_relay_set_and_reads_states():
    states = [False, True, True, False]
    relay, direct = _client(replies={
        "relay_set": {"status": "ok", "states": states},
        "relay_status": {"status": "ok", "states": states},
    })
    relay.source_on()
    assert relay._client.sent[0] == {"cmd": "relay_set", "channel": "source_on", "on": True}
    assert relay.read_relay_status() == states
    assert relay._client.sent[-1] == {"cmd": "relay_status", "fresh": True}
    assert relay.read_source_status() is True and relay.read_magnet_status() is True
    assert direct.calls == []


def test_client_enable_goes_through_the_interlock_and_can_be_refused():
    relay, direct = _client(bare={"ENABLE_MAGNETS": {"status": "refused", "reason": "tripped"}})
    with pytest.raises(er.RelayRefused) as info:
        relay.enable_magnets()
    assert info.value.reason == "tripped"
    assert direct.calls == []                        # never around the interlock


def test_client_falls_back_to_the_board_with_an_old_server():
    relay, direct = _client(replies={"relay_set": OLD, "relay_status": OLD, "artiq_restart": OLD})
    relay.source_on()
    relay.source_off()
    relay.read_relay_status()
    relay.restart_artiq(0.0, 0.0)
    assert direct.calls == ["set_channel", "read_relay_status", "source_off",
                            "read_relay_status", "restart_artiq"]


def test_client_kill_without_any_interlock_server_goes_direct():
    direct = FakeDirect()
    relay = er.EthernetRelay(direct_factory=lambda: direct)

    def no_server():
        raise er.RelayServerUnavailable("interlock server not found (fake)")
    relay._interlock = no_server
    relay.kill_magnets()
    relay.source_off()
    assert direct.calls == ["kill_magnets", "source_off"]
    with pytest.raises(er.RelayServerUnavailable):
        relay.source_on()                            # switching ON never goes around it
    with pytest.raises(er.RelayServerUnavailable):
        relay.enable_magnets()


def test_client_kill_retries_a_silent_server_then_goes_direct():
    relay, direct = _client(fail=OSError("timed out (fake)"))
    relay.SAFE_RETRY_BUDGET_S = 0.1
    relay.kill_magnets()
    assert len([c for c in relay._client.sent if c == "DISABLE_MAGNETS"]) >= 2
    assert direct.calls == ["kill_magnets"]


def test_client_kill_confirmed_by_the_server_never_goes_direct():
    relay, direct = _client(bare={"DISABLE_MAGNETS": {"status": "ok"}})
    relay.kill_magnets()
    assert direct.calls == []


def test_client_restart_waits_for_the_job():
    polls = []

    def job(obj):
        polls.append(obj)
        return {"state": "done" if len(polls) >= 3 else "running"}
    relay, direct = _client(replies={"artiq_restart": {"status": "started", "job_id": "j1"},
                                     "relay_job": job})
    relay.JOB_POLL_S = 0.01
    relay.toggle_artiq_main_power(t_wait=0.0)
    assert relay._client.sent[0] == {"cmd": "artiq_restart", "which": "main",
                                     "t_wait": 0.0, "t_between": 0.0}
    assert len(polls) == 3


def test_client_restart_busy_is_an_error():
    relay, _ = _client(replies={"artiq_restart": {"status": "busy", "message": "already running"}})
    with pytest.raises(er.RelayCommandFailed):
        relay.restart_artiq()


def test_client_connect_and_close_do_nothing():
    relay, direct = _client()
    relay.connect()
    relay.close()
    assert relay._client.sent == [] and direct.calls == []


def test_the_package_export_is_the_client():
    import kexp
    assert kexp.EthernetRelay is er.EthernetRelay
    assert getattr(kexp.EthernetRelay, "IS_RELAY_CLIENT", False)
