"""Interlock server on ComLink: comes up without its COM port, keeps retrying
it, never enables the magnets or resets the interlock on a reconnect, trips on
stale data in every link state, and refuses a COM Disconnect while the magnets
are enabled.

Fakes only: the serial class, the port list and the relay are stand-ins; the
singleton mutex is never taken; the TCP server binds 127.0.0.1 port 0 and its
beacon is a no-op (conftest + here).  Nothing touches real hardware.
"""
from __future__ import annotations

import importlib
import json
import socket
import sys
import threading
import time
from types import SimpleNamespace

import pytest
import serial
import serial.tools.list_ports

from kexp.util.guis.interlock import interlock_safe_mode as _sm
from kexp.util.guis.interlock import interlock_service as isvc
from kexp.util.guis.interlock.interlock_client import InterlockClient

PORT = "COMFAKE7"
FRAME = (b"Flowmeter 1 reads 1.00V/Flowmeter 2 reads 1.10V/Flowmeter 3 reads 1.20V/"
         b"Flowmeter 4 reads 1.30V/Temp is 300.0k/")


def _until(pred, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeRelay:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.kills = 0
        self.enables = 0
        self.fail_reads = False

    def kill_magnets(self):
        self.kills += 1
        self.enabled = False

    def enable_magnets(self):
        self.enables += 1
        self.enabled = True

    def read_magnet_status(self, retries=None, timeout=None):
        if self.fail_reads:
            raise OSError("relay unreachable (fake)")
        return self.enabled


class FakeSerial:
    def __init__(self, bus, timeout):
        self.bus = bus
        self.timeout = timeout
        self.is_open = True
        self.writes = []
        self.fail_next_read = False

    def read(self, n):
        if not self.is_open:
            raise serial.SerialException("port closed (fake)")
        if self.fail_next_read:
            self.fail_next_read = False
            raise serial.SerialException("ClearCommError failed (fake unplug)")
        if self.bus.feed.is_set():
            time.sleep(0.01)
            return FRAME
        time.sleep(self.timeout)
        return b""

    def write(self, data):
        self.writes.append(bytes(data))
        self.bus.writes.append(bytes(data))

    def close(self):
        self.is_open = False


class FakeBus:
    """The port list and serial.Serial stand-in for one test."""

    def __init__(self, present):
        self.present = set(present)
        self.feed = threading.Event()        # PLC frames flowing
        self.open_gate = None                # Event an open waits on (hang)
        self.opens = 0
        self.ports = []
        self.writes = []

    def comports(self):
        return [SimpleNamespace(device=p) for p in sorted(self.present)]

    def serial(self, port, baudrate, timeout):
        self.opens += 1
        if self.open_gate is not None:
            self.open_gate.wait(5.0)
        if port not in self.present:
            raise serial.SerialException(f"could not open port '{port}': FileNotFoundError (fake)")
        ser = FakeSerial(self, timeout)
        self.ports.append(ser)
        return ser

    @property
    def current(self):
        return self.ports[-1]


@pytest.fixture
def make(monkeypatch):
    """make(present=..., relay=..., stale=...) -> (service, bus, relay)."""
    made = []
    monkeypatch.setattr(isvc.InterlockService, "acquire_singleton_mutex", lambda self: True)
    monkeypatch.setattr(isvc.InterlockService, "release_singleton_mutex", lambda self: None)
    monkeypatch.setattr(isvc._PLCLink, "BACKOFF_S", (0.05,))
    from beacon.discovery import server as dserver
    monkeypatch.setattr(dserver.NetServer, "_start_beacon", lambda self: None)

    def _make(present=False, relay=None, stale=30.0, start=True):
        bus = FakeBus([PORT] if present else [])
        monkeypatch.setattr(serial, "Serial", bus.serial)
        monkeypatch.setattr(serial.tools.list_ports, "comports", bus.comports)
        relay = relay or FakeRelay(enabled=True)
        cfg = isvc.InterlockConfig(
            com_port=PORT, com_timeout_s=0.05, stale_threshold_s=stale,
            watchdog_check_interval_s=60.0, heartbeat_interval_s=60.0,
            reset_debounce_s=0.0,
        )
        svc = isvc.InterlockService(relay, cfg)
        made.append((svc, bus))
        if start:
            assert svc.start() is True
        return svc, bus, relay

    yield _make
    for svc, bus in made:
        if bus.open_gate is not None:
            bus.open_gate.set()
        svc.stop()


def _state(svc):
    return svc.get_snapshot()["state"]


def _com(svc):
    return svc.get_snapshot()["com"]


# ---------------------------------------------------------------------------
# Boot without the port
# ---------------------------------------------------------------------------

def test_boot_without_port_comes_up_kills_once_and_refuses_enable(make):
    t0 = time.monotonic()
    svc, bus, relay = make(present=False, relay=FakeRelay(enabled=True))
    assert time.monotonic() - t0 < 1.0             # start() never waits for the port
    assert relay.kills == 1                        # made safe exactly once at boot
    assert relay.enabled is False
    snap = svc.get_snapshot()
    assert snap["state"] == _sm.STATE_WARMUP       # not the terminal safe mode
    assert snap["safe_mode_reason"] is None
    assert PORT in snap["message"]
    assert snap["com"]["config_valid"] is False
    assert snap["com"]["status"] in ("connecting", "error")
    # Enable refused until real PLC data flows; reset has no port to write to.
    assert svc.enable_magnets()["status"] == "refused"
    assert svc.enable_magnets()["reason"] == "no_plc_data"
    assert relay.enables == 0
    assert svc.reset_interlock()["status"] == "error"
    # Still exactly one boot kill (no stale trip at 30 s threshold).
    time.sleep(0.2)
    assert relay.kills == 1


def test_boot_without_port_and_relay_unreachable_is_still_safe_mode(make):
    relay = FakeRelay(enabled=True)
    relay.fail_reads = True
    svc, bus, relay = make(present=False, relay=relay)
    snap = svc.get_snapshot()
    assert snap["state"] == _sm.STATE_SAFE_MODE
    assert _sm.REASON_RELAY_UNREACHABLE_AT_BOOT in snap["safe_mode_reason"]
    assert _sm.REASON_BAD_COM_PORT in snap["safe_mode_reason"]
    assert relay.kills == 1
    assert snap["com"]["config_valid"] is False
    assert svc.com_connect()["status"] == "refused"   # safe mode opens no port
    time.sleep(0.2)
    assert bus.opens == 0


def test_link_keeps_retrying_and_connects_when_port_appears(make):
    svc, bus, relay = make(present=False)
    assert _until(lambda: bus.opens >= 3)          # retries on its backoff
    assert _com(svc)["status"] == "error"
    bus.present.add(PORT)
    assert _until(lambda: _com(svc)["status"] == "connected")
    assert _com(svc)["config_valid"] is True
    # Connected, but no PLC frame yet: still warmup, Enable still refused.
    assert _state(svc) == _sm.STATE_WARMUP
    assert svc.enable_magnets()["status"] == "refused"
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert relay.enables == 0 and relay.enabled is False
    assert bus.writes == []                        # no automatic reset ('O')
    # Only now may a person enable them.
    assert svc.enable_magnets("person")["status"] == "ok"
    assert relay.enables == 1


def test_reconnect_never_enables_magnets_or_resets_interlock(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), stale=0.3)
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert svc.enable_magnets("person")["status"] == "ok"
    # PLC goes quiet -> stale trip kills the magnets.
    bus.feed.clear()
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    assert _until(lambda: relay.enabled is False)
    enables = relay.enables
    # The port fails and comes back; the PLC talks again.
    bus.current.fail_next_read = True
    assert _until(lambda: bus.opens >= 2 and _com(svc)["status"] == "connected")
    bus.feed.set()
    time.sleep(0.3)
    assert _state(svc) == _sm.STATE_TRIPPED        # the trip latch is untouched
    assert relay.enables == enables and relay.enabled is False
    assert bus.writes == []                        # no 'O' to the PLC


# ---------------------------------------------------------------------------
# Staleness in every link state
# ---------------------------------------------------------------------------

def test_stale_trips_while_held(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), stale=0.4)
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert svc.com_disconnect("person")["status"] == "ok"
    assert _com(svc)["status"] == "held"
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    assert relay.kills >= 1


def test_stale_trips_while_in_error(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), stale=0.4)
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert svc.enable_magnets("person")["status"] == "ok"
    bus.present.discard(PORT)                      # unplugged: reopens fail
    bus.current.fail_next_read = True
    assert _until(lambda: _com(svc)["status"] == "error")
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    assert _until(lambda: relay.enabled is False)


def test_stale_trips_while_reconnecting(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), stale=0.4)
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert svc.enable_magnets("person")["status"] == "ok"
    bus.open_gate = threading.Event()              # the reopen hangs
    bus.current.fail_next_read = True
    assert _until(lambda: _com(svc)["status"] == "connecting")
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    assert _until(lambda: relay.enabled is False)
    # The poll loop kept running through the hanging open (no watchdog stall).
    age = time.monotonic() - svc._last_loop_iteration_monotonic
    assert age < 1.0


# ---------------------------------------------------------------------------
# Dashboard Disconnect / Connect
# ---------------------------------------------------------------------------

def test_com_disconnect_refused_while_enabled_then_held_then_connect(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=True))
    assert _until(lambda: _com(svc)["status"] == "connected")
    reply = svc.com_disconnect("person")
    assert reply["status"] == "refused"
    assert "magnets are enabled" in reply["message"]
    assert _com(svc)["status"] == "connected"
    # Relay unreadable: refused too (cannot confirm they are off).
    relay.enabled = False
    relay.fail_reads = True
    reply = svc.com_disconnect("person")
    assert reply["status"] == "refused" and "unknown" in reply["message"]
    assert _com(svc)["status"] == "connected"
    # Disabled: allowed, then held -- no reopen of any kind.
    relay.fail_reads = False
    reply = svc.com_disconnect("person")
    assert reply["status"] == "ok"
    opens = bus.opens
    assert bus.current.is_open is False
    time.sleep(0.4)
    snap = _com(svc)
    assert snap["status"] == "held" and snap["held"] is True
    assert bus.opens == opens
    # Connect releases the hold and opens the port.
    reply = svc.com_connect("person")
    assert reply["status"] == "ok"
    assert _until(lambda: _com(svc)["status"] == "connected")
    assert bus.opens == opens + 1
    assert relay.enables == 0 and bus.writes == []


# ---------------------------------------------------------------------------
# TCP server + client
# ---------------------------------------------------------------------------

def _server_module(monkeypatch, tmp_path):
    name = "kexp.util.guis.interlock.interlock_server"
    if name not in sys.modules:
        # Importing the server configures logging; keep it off the live log.
        import waxx.util.dashboard.logging_setup as ls
        monkeypatch.setattr(ls, "configure_server_logging",
                            lambda server_id, level=None: tmp_path / f"{server_id}.log")
        importlib.import_module(name)
    return sys.modules[name]


def _client_for(port):
    client = InterlockClient.__new__(InterlockClient)   # no discovery
    client.host, client.port, client.timeout = "127.0.0.1", port, 1.5
    return client


def test_server_answers_with_port_missing_and_beacons_com_state(make, monkeypatch, tmp_path):
    srv_mod = _server_module(monkeypatch, tmp_path)
    svc, bus, relay = make(present=False, relay=FakeRelay(enabled=True))
    tcp = srv_mod.InterlockTCPServer(svc, host="127.0.0.1", port=0)
    svc.attach_beacon_server(tcp)
    tcp.start()
    try:
        client = _client_for(tcp._port)
        snap = client.get_snapshot()
        assert snap["state"] == _sm.STATE_WARMUP
        assert snap["com"]["status"] in ("connecting", "error")
        assert tcp._waxx_beacon_extra["com_port"] == PORT
        assert tcp._waxx_beacon_extra["com"] in ("connecting", "error")
        # Relay reads disabled (boot kill): Disconnect allowed, then held.
        ok, msg = client.com_disconnect()
        assert ok is True and "held" in msg
        assert _until(lambda: tcp._waxx_beacon_extra["com"] == "held")
        bus.present.add(PORT)
        time.sleep(0.3)
        assert bus.ports == []                     # held: never opened
        ok, msg = client.com_connect()
        assert ok is True
        assert _until(lambda: tcp._waxx_beacon_extra["com"] == "connected")
        relay.enabled = True
        ok, msg = client.com_disconnect()
        assert ok is False and "magnets are enabled" in msg
        assert relay.enables == 0
    finally:
        tcp.stop()


def test_client_com_replies_parse(monkeypatch):
    client = _client_for(1)
    replies = {
        "COM_CONNECT": {"status": "ok", "message": "connecting COMFAKE7"},
        "COM_DISCONNECT": {"status": "refused", "reason": "disconnect_refused",
                           "message": "magnets are enabled: disable them first"},
    }
    sent = []
    monkeypatch.setattr(client, "_send_json", lambda cmd: sent.append(cmd) or replies[cmd])
    assert client.com_connect() == (True, "connecting COMFAKE7")
    assert client.com_disconnect() == (False, "magnets are enabled: disable them first")
    replies["COM_DISCONNECT"] = {"status": "error"}
    assert client.com_disconnect() == (False, "error")
    assert sent == ["COM_CONNECT", "COM_DISCONNECT", "COM_DISCONNECT"]


def test_client_com_raises_on_network_failure():
    with socket.socket() as s:                     # a port nobody listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    client = _client_for(port)
    client._rediscover = lambda timeout=1.0: False  # no discovery in tests
    with pytest.raises(OSError):
        client.com_connect()
    with pytest.raises(OSError):
        client.com_disconnect()
