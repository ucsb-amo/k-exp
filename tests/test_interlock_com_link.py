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
RELAY_LABEL = "10.255.255.1:2101 (fake)"
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
    """The board (EthernetRelayDirect's one-contact calls).  Relay 2 is the
    magnet relay; ``enabled`` is its state."""

    def __init__(self, enabled=True):
        self.states = [False, bool(enabled), False, False]
        self.kills = 0
        self.enables = 0
        self.writes = []
        self.contacts = 0
        self.fail_reads = False
        self.down = False          # every call refused, like a relay not answering

    @property
    def enabled(self):
        return self.states[1]

    @enabled.setter
    def enabled(self, value):
        self.states[1] = bool(value)

    def _check_down(self):
        self.contacts += 1
        if self.down:
            raise ConnectionRefusedError(10061, "actively refused (fake)")

    def _write(self, idx, on):
        self.writes.append((idx, bool(on)))
        if idx == 2:
            if on:
                self.enables += 1
            else:
                self.kills += 1
        self.states[idx - 1] = bool(on)

    def _read(self):
        if self.fail_reads:
            raise OSError("relay unreachable (fake)")
        return list(self.states)

    def read_relay_status(self, retries=None, timeout=None):
        self._check_down()
        return self._read()

    def read_magnet_status(self, retries=None, timeout=None):
        self._check_down()
        return self._read()[1]

    def kill_magnets_and_read(self, retries=None, timeout=None):
        self._check_down()
        self._write(2, False)
        return self._read()[1]

    def set_channel_and_read_all(self, idx, on, retries=None, timeout=None):
        self._check_down()
        self._write(idx, on)
        return self._read()

    def set_channels_and_read_all(self, states, retries=None, timeout=None):
        self._check_down()
        for idx, on in states.items():
            self._write(idx, on)
        return self._read()


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
            frame = self.bus.frame
            return frame() if callable(frame) else frame
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
        self.frame = FRAME                   # what each read returns (bytes or callable)
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
    monkeypatch.setattr(isvc, "_RELAY_POLL_INTERVAL_S", 0.05)
    monkeypatch.setattr(isvc, "_PLC_CLEAR_S", 0.4)
    from beacon.discovery import server as dserver
    monkeypatch.setattr(dserver.NetServer, "_start_beacon", lambda self: None)

    def _make(present=False, relay=None, stale=30.0, start=True, **cfg_overrides):
        bus = FakeBus([PORT] if present else [])
        monkeypatch.setattr(serial, "Serial", bus.serial)
        monkeypatch.setattr(serial.tools.list_ports, "comports", bus.comports)
        relay = relay or FakeRelay(enabled=True)
        cfg_kwargs = dict(
            com_port=PORT, com_timeout_s=0.05, stale_threshold_s=stale,
            watchdog_check_interval_s=60.0, heartbeat_interval_s=60.0,
            reset_debounce_s=0.0, relay_label=RELAY_LABEL,
        )
        cfg_kwargs.update(cfg_overrides)
        cfg = isvc.InterlockConfig(**cfg_kwargs)
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


# ---------------------------------------------------------------------------
# Relay not answering
# ---------------------------------------------------------------------------

def test_boot_with_relay_down_runs_reports_it_and_recovers(make):
    relay = FakeRelay(enabled=True)
    relay.down = True
    t0 = time.monotonic()
    svc, bus, relay = make(present=True, relay=relay)
    assert time.monotonic() - t0 < 1.0             # comes up; no safe mode
    snap = svc.get_snapshot()
    assert snap["state"] == _sm.STATE_RELAY_DOWN
    assert snap["relay_ok"] is False and snap["relay_down_since"] is not None
    assert RELAY_LABEL in snap["message"] and "not answering" in snap["message"]
    assert snap["safe_mode_reason"] is None
    assert snap["magnets_enabled"] is None         # never read
    # PLC monitoring runs meanwhile; the relay note still shows, Enable refused.
    bus.feed.set()
    assert _until(lambda: svc.get_snapshot()["interlock_state"] == _sm.STATE_OK)
    snap = svc.get_snapshot()
    assert snap["state"] == _sm.STATE_RELAY_DOWN
    assert snap["temperature_c"] is not None
    reply = svc.enable_magnets("person")
    assert reply["status"] == "refused" and reply["reason"] == "relay_not_answering"
    # The relay answers again: normal, magnet relay left as it was (IT10).
    relay.down = False
    assert _until(lambda: svc.get_snapshot()["state"] == _sm.STATE_OK)
    snap = svc.get_snapshot()
    assert snap["relay_ok"] is True and snap["relay_error"] is None
    assert snap["magnets_enabled"] is True
    assert relay.kills == 0 and relay.enables == 0 and bus.writes == []


def test_relay_down_with_port_missing_kills_once_when_relay_answers(make):
    relay = FakeRelay(enabled=True)
    relay.down = True
    svc, bus, relay = make(present=False, relay=relay)
    snap = svc.get_snapshot()
    assert snap["state"] == _sm.STATE_RELAY_DOWN
    assert PORT in snap["message"]                 # the warmup note is kept
    assert snap["com"]["config_valid"] is False
    time.sleep(0.2)
    assert relay.kills == 0                        # nothing reaches the relay
    relay.down = False
    assert _until(lambda: relay.kills == 1)        # the owed startup kill
    assert relay.enabled is False
    assert _until(lambda: svc.get_snapshot()["state"] == _sm.STATE_WARMUP)
    time.sleep(0.2)
    assert relay.kills == 1 and relay.enables == 0


def test_relay_dropping_out_later_is_reported_after_three_failures(make, monkeypatch):
    # The relay's usual short refusals last one or two polls: not an outage.
    monkeypatch.setattr(isvc, "_RELAY_POLL_INTERVAL_S", 60.0)   # the test polls by hand
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False))
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    relay.down = True
    for n in (1, 2):
        with pytest.raises(ConnectionRefusedError):
            svc._owner.read_all()
        assert _state(svc) == _sm.STATE_OK, f"reported down after {n} failure(s)"
    with pytest.raises(ConnectionRefusedError):
        svc._owner.read_all()
    assert _state(svc) == _sm.STATE_RELAY_DOWN     # three in a row: reported
    assert svc.enable_magnets("person")["reason"] == "relay_not_answering"
    relay.down = False
    svc._owner.read_all()
    assert _state(svc) == _sm.STATE_OK             # one success clears it
    assert relay.kills == 0 and relay.enables == 0 # nothing switched by the outage


def test_snapshots_never_contact_the_relay(make, monkeypatch):
    monkeypatch.setattr(isvc, "_RELAY_POLL_INTERVAL_S", 60.0)
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=True))
    contacts = relay.contacts
    for _ in range(50):
        snap = svc.get_snapshot()
    assert relay.contacts == contacts
    assert snap["magnets_enabled"] is True
    assert snap["relay"]["relays"]["magnet_enabled"] is True
    assert snap["relay"]["link"] == "ok"


def test_trip_while_relay_down_keeps_tripped_state_with_relay_note(make):
    relay = FakeRelay(enabled=True)
    relay.down = True
    svc, bus, relay = make(present=True, relay=relay, stale=0.3)
    assert _until(lambda: svc.get_snapshot()["state"] == _sm.STATE_TRIPPED)
    snap = svc.get_snapshot()
    assert "not answering" in snap["message"]
    relay.down = False
    assert _until(lambda: relay.enabled is False)  # the trip's kill lands


def test_watchdog_does_not_exit_without_a_poll_loop(make, monkeypatch):
    exits = []
    monkeypatch.setattr(isvc.os, "_exit", lambda code: exits.append(code))
    svc, bus, relay = make(present=True, start=False,
                           watchdog_check_interval_s=0.05, watchdog_loop_grace_s=0.1)
    svc.enter_safe_mode("test reason")
    svc._start_watchdog_and_heartbeat()
    time.sleep(0.5)
    assert exits == []


def test_link_keeps_retrying_and_connects_when_port_appears(make):
    svc, bus, relay = make(present=False)
    assert _until(lambda: bus.opens >= 3)          # retries on its backoff
    # Between retries it reads "error"; during each 50 ms retry, "connecting"
    # (one sample could land in either -- a race since this test was written).
    assert _until(lambda: _com(svc)["status"] == "error")
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


TRIPPED_FRAME = FRAME + b"\r\nI TRIPPED\r\n"


def test_reconnect_rechecks_status_but_never_enables_magnets(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), stale=0.6)
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert svc.enable_magnets("person")["status"] == "ok"
    # PLC goes quiet -> stale trip kills the magnets.
    bus.feed.clear()
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    assert _until(lambda: relay.enabled is False)
    enables = relay.enables
    # The port fails and comes back; the PLC talks again, reporting no trip.
    bus.current.fail_next_read = True
    assert _until(lambda: bus.opens >= 2 and _com(svc)["status"] == "connected")
    bus.feed.set()
    assert svc.get_snapshot()["plc_recheck_since"] is not None
    # Not on the first frame: only after _PLC_CLEAR_S of data with no trip.
    assert _until(lambda: _state(svc) == _sm.STATE_OK, timeout=5.0)
    snap = svc.get_snapshot()
    assert snap["plc_recheck_since"] is None and snap["plc_inhibiting"] is False
    assert relay.enables == enables and relay.enabled is False   # magnets stay off
    assert bus.writes == []                        # no 'O' to the PLC
    assert _until(lambda: svc.enable_magnets("person")["status"] == "ok")


def test_reconnect_with_plc_still_tripped_stays_tripped_until_plc_reset(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False))
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    bus.frame = TRIPPED_FRAME                      # the PLC trips and latches
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    assert svc.get_snapshot()["plc_inhibiting"] is True
    bus.current.fail_next_read = True              # COM drops and comes back
    assert _until(lambda: bus.opens >= 2 and _com(svc)["status"] == "connected")
    time.sleep(1.0)                                # > _PLC_CLEAR_S of tripped frames
    snap = svc.get_snapshot()
    assert snap["state"] == _sm.STATE_TRIPPED
    assert "PLC still reports a trip" in snap["message"]
    assert svc.enable_magnets("person")["status"] == "refused"
    # A person resets the PLC (USB re-enumerates): clean frames after a reconnect.
    bus.frame = FRAME
    bus.current.fail_next_read = True
    assert _until(lambda: _state(svc) == _sm.STATE_OK, timeout=5.0)
    assert svc.get_snapshot()["plc_inhibiting"] is False
    assert relay.enables == 0 and relay.enabled is False


def test_without_reconnect_a_trip_stays_latched(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), stale=0.6)
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert _until(lambda: svc.get_snapshot()["plc_recheck_since"] is None, timeout=5.0)
    bus.feed.clear()                               # silent PLC, port stays open
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    bus.feed.set()
    time.sleep(1.2)
    assert _state(svc) == _sm.STATE_TRIPPED


def test_trip_text_split_across_reads_is_found(make):
    svc, bus, relay = make(present=True, start=False)
    first = isvc._Sample(epoch=0.0, flow_v={1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}, temperature_k=300.0)
    assert svc._track_plc_stream(FRAME + b"\r\nI TRIP", first)[0] is False
    assert svc._track_plc_stream(b"PED\r\n" + FRAME, first)[0] is True
    assert svc._plc_latched is True
    # The tail that held the match is not matched again by the next read.
    assert svc._track_plc_stream(FRAME, first)[0] is False
    assert svc._track_plc_stream(b"SHUTTING OFF POWER SUPPLY DUE TO TEMPERATURE\r\n", None)[0]


def _temp_frame(t_k):
    return (b"Flowmeter 1 reads 1.00V/Flowmeter 2 reads 1.10V/Flowmeter 3 reads 1.20V/"
            b"Flowmeter 4 reads 1.30V/Temp is " + f"{t_k:.5f}".encode() + b"k/")


def _moving_frame(n):
    """Every reading differs from the previous frame's."""
    flows = "".join(f"Flowmeter {m} reads {1.0 + m * 0.1 + n % 2 * 0.01:.2f}V/" for m in (1, 2, 3, 4))
    return flows.encode() + f"Temp is {300.0 + n * 1e-5:.5f}k/".encode()


def test_railed_read_trips_kills_and_holds_until_the_value_changes(make):
    # Flows constant in every frame; only the temperature can move.
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), railed_window_s=0.8)
    temps = iter(range(10**6))
    bus.frame = lambda: _temp_frame(300.0 + next(temps) * 1e-5)
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert svc.enable_magnets("person")["status"] == "ok"
    # The flows never change: railed after railed_window_s -> trip + kill.
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED, timeout=5.0)
    snap = svc.get_snapshot()
    assert "Opta read railed" in snap["message"]
    assert set(snap["railed"]) == {"flow 1", "flow 2", "flow 3", "flow 4"}
    assert "temperature" not in snap["railed"]
    assert snap["railed"]["flow 1"]["value"] == 1.0
    assert _until(lambda: relay.enabled is False)
    reply = svc.enable_magnets("person")
    assert reply["status"] == "refused" and reply["reason"] == "opta_read_railed"
    # A reconnect does not clear it while the read is railed.
    bus.current.fail_next_read = True
    assert _until(lambda: bus.opens >= 2 and _com(svc)["status"] == "connected")
    time.sleep(1.0)
    snap = svc.get_snapshot()
    assert snap["state"] == _sm.STATE_TRIPPED and "Opta read is railed" in snap["message"]
    # The reads move again: railed clears; the pending recheck then returns to ok.
    bus.frame = lambda: _moving_frame(next(temps))
    assert _until(lambda: svc.get_snapshot()["railed"] == {}, timeout=5.0)
    assert _until(lambda: _state(svc) == _sm.STATE_OK, timeout=5.0)
    assert relay.enabled is False and relay.enables == 1


def test_railed_run_restarts_after_a_gap_in_reports(make):
    svc, bus, relay = make(present=True, start=False, railed_window_s=1.0, stale=0.2)
    s = isvc._Sample(epoch=0.0, temperature_k=300.0)
    assert svc._track_railed(s) is None
    time.sleep(0.3)                                # a gap longer than stale_threshold_s
    assert svc._track_railed(s) is None
    time.sleep(0.15)
    assert svc._track_railed(s) is None            # run restarted at the gap: 0.15 s held
    assert svc._railed == {}


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
    assert _until(lambda: relay.kills >= 1)       # the kill thread starts just after


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


def test_com_disconnect_allowed_while_tripped_with_relay_busy(make):
    # Stale PLC data -> tripped; the kill thread keeps the relay lock busy.  The
    # Disconnect must not wait on the relay then (11-17: refused as "relay busy").
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False), stale=0.4)
    assert _until(lambda: _com(svc)["status"] == "connected")
    assert _until(lambda: _state(svc) == _sm.STATE_TRIPPED)
    assert svc._owner.lock.acquire(timeout=2.0)
    try:
        reply = svc.com_disconnect("person")
    finally:
        svc._owner.lock.release()
    assert reply["status"] == "ok"
    assert _com(svc)["status"] == "held"


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


def test_server_answers_promptly_while_relay_down(make, monkeypatch, tmp_path):
    srv_mod = _server_module(monkeypatch, tmp_path)
    relay = FakeRelay(enabled=True)
    relay.down = True
    svc, bus, relay = make(present=True, relay=relay)
    tcp = srv_mod.InterlockTCPServer(svc, host="127.0.0.1", port=0)
    tcp.start()
    try:
        snap = _client_for(tcp._port).get_snapshot()
        assert snap["state"] == _sm.STATE_RELAY_DOWN
        assert RELAY_LABEL in snap["message"]
    finally:
        tcp.stop()


# ---------------------------------------------------------------------------
# The relay's owner: every kill retried until confirmed; kills first
# ---------------------------------------------------------------------------

def test_manual_kill_with_relay_down_hands_over_and_lands_later(make, monkeypatch):
    monkeypatch.setattr(isvc, "_RPC_KILL_BUDGET_S", 0.3)
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=True))
    relay.down = True
    t0 = time.monotonic()
    reply = svc.disable_magnets("person")
    assert time.monotonic() - t0 < 2.0
    assert reply["status"] == "error" and "keeps retrying" in reply["message"]
    assert relay.enabled is True                   # not reached yet
    relay.down = False
    assert _until(lambda: relay.enabled is False)  # the persistent kill landed


def test_manual_kill_is_confirmed_by_a_read_back(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=True))
    assert svc.disable_magnets("person") == {"status": "ok"}
    assert relay.enabled is False and relay.kills == 1


def test_emergency_kill_retries_until_the_relay_answers(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=True))
    relay.down = True
    threading.Timer(0.3, lambda: setattr(relay, "down", False)).start()
    svc._emergency_trip("test")                    # was a single attempt before 11-17
    assert relay.enabled is False


def test_unconfirmed_startup_kill_stays_owed_and_lands(make, monkeypatch):
    monkeypatch.setattr(isvc, "_STARTUP_KILL_BUDGET_S", 0.2)

    class KillFails(FakeRelay):
        refuse_kills = True

        def kill_magnets_and_read(self, retries=None, timeout=None):
            if self.refuse_kills:
                self.contacts += 1
                raise ConnectionRefusedError(10061, "refused (fake)")
            return super().kill_magnets_and_read(retries, timeout)

    relay = KillFails(enabled=True)
    svc, bus, relay = make(present=False, relay=relay)    # COM missing: kill owed
    assert relay.enabled is True and svc._startup_kill_owed is True
    assert "kill owed" in svc.get_snapshot()["message"]
    relay.refuse_kills = False
    assert _until(lambda: relay.enabled is False)
    assert _until(lambda: svc._startup_kill_owed is False)


def test_enable_waiting_for_the_relay_loses_to_a_trip(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False))
    bus.feed.set()
    assert _until(lambda: _state(svc) == _sm.STATE_OK)
    assert svc._owner.lock.acquire(timeout=2.0)    # the relay is busy
    replies = []
    t = threading.Thread(target=lambda: replies.append(svc.enable_magnets("person")))
    t.start()
    time.sleep(0.1)                                 # Enable passed its first check, waits
    svc._trip("test trip")                         # the trip comes while it waits
    time.sleep(0.1)
    svc._owner.lock.release()
    t.join(5.0)
    assert replies and replies[0]["status"] == "refused"
    assert replies[0]["reason"] in ("tripped", "kill_in_progress")
    assert relay.enables == 0 and relay.enabled is False


def test_relay_commands_on_the_service(make, monkeypatch):
    monkeypatch.setattr(isvc, "_RELAY_POLL_INTERVAL_S", 60.0)
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=True))
    reply = svc.relay_set("source_on", True, "person")
    assert reply["status"] == "ok" and reply["relays"]["source_on"] is True
    assert relay.states[2] is True
    reply = svc.relay_set("magnet_enabled", True, "person")
    assert reply["status"] == "refused" and relay.enables == 0
    assert svc.relay_set("nonsense", True)["status"] == "error"
    assert svc.relay_set("source_on", "yes")["status"] == "error"
    contacts = relay.contacts
    assert svc.relay_status(fresh=False)["states"] == relay.states
    assert relay.contacts == contacts               # cached
    assert svc.relay_status(fresh=True)["stale"] is False
    assert svc.relay_status(fresh=True)["age_s"] >= 0  # rate-limited: the cache
    assert relay.contacts == contacts + 1


def test_artiq_restart_job_and_its_power_relays_are_fenced(make, monkeypatch):
    monkeypatch.setattr(isvc, "_RELAY_POLL_INTERVAL_S", 60.0)
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False))
    reply = svc.artiq_restart("satellites", 0.3, 0.0, "person")
    assert reply["status"] == "started"
    assert svc.relay_set("artiq_main_power_cut", True)["reason"] == "artiq_restart_running"
    assert svc.relay_set("source_on", True)["status"] == "ok"   # the source is not fenced
    assert _until(lambda: svc.relay_job(reply["job_id"])["state"] == "done")
    assert relay.states[3] is False
    assert svc.get_snapshot()["relay"]["job"]["state"] == "done"


def test_stop_during_a_restart_restores_crate_power(make):
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False))
    svc.artiq_restart("main", 30.0, 0.0, "person")
    assert _until(lambda: relay.states[0] is True)
    t0 = time.monotonic()
    svc.stop()
    assert time.monotonic() - t0 < 4.0            # inside the dashboard's graceful stop
    assert relay.states[0] is False


def test_server_relay_json_commands_and_old_commands(make, monkeypatch, tmp_path):
    srv_mod = _server_module(monkeypatch, tmp_path)
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False))
    tcp = srv_mod.InterlockTCPServer(svc, host="127.0.0.1", port=0)
    tcp.start()
    try:
        client = _client_for(tcp._port)
        reply = client.relay_set("source_on", True)
        assert reply["status"] == "ok" and reply["relays"]["source_on"] is True
        assert client.relay_status()["relays"]["source_on"] is True
        reply = client.request({"cmd": "relay_set", "channel": "magnet_enabled", "on": True})
        assert reply["status"] == "refused"
        reply = client.request({"cmd": "no_such"})
        assert reply["message"].startswith("unknown command")
        assert client._send_json("{not json")["status"] == "error"
        job = client.artiq_restart("main", 0.1)
        assert job["status"] == "started"
        assert _until(lambda: client.relay_job(job["job_id"])["state"] == "done")
        assert client.get_snapshot()["relay"]["relays"]["artiq_main_power_cut"] is False
        assert client.disable_magnets()["status"] == "ok"       # bare commands unchanged
    finally:
        tcp.stop()


def test_new_client_against_this_server_end_to_end(make, monkeypatch, tmp_path):
    from kexp.control.ethernet_relay import EthernetRelay, RelayRefused
    srv_mod = _server_module(monkeypatch, tmp_path)
    svc, bus, relay = make(present=True, relay=FakeRelay(enabled=False))
    tcp = srv_mod.InterlockTCPServer(svc, host="127.0.0.1", port=0)
    tcp.start()

    def no_direct():
        raise AssertionError("the client went around the server")
    try:
        er = EthernetRelay(client=_client_for(tcp._port), direct_factory=no_direct)
        er.source_on()
        assert er.read_source_status() is True
        er.source_off()
        assert relay.states[2] is False
        with pytest.raises(RelayRefused):
            er.enable_magnets()                     # warmup: no PLC frame yet
        er.kill_magnets()
        er.JOB_POLL_S = 0.05
        er.toggle_artiq_satellites_power(t_wait=0.1)
        assert relay.states[3] is False
        assert er.read_relay_status() == relay.states
    finally:
        tcp.stop()


def test_full_stack_on_a_fake_board(make, monkeypatch, tmp_path):
    """client EthernetRelay -> interlock TCP server -> service -> RelayOwner ->
    EthernetRelayDirect -> a fake NCD board on 127.0.0.1 (real sockets, real
    packet framing).  Nothing else connects to the board."""
    from test_relay_owner import FakeBoard
    from kexp.control.ethernet_relay import EthernetRelay, EthernetRelayDirect
    board = FakeBoard()
    board.states = [False, True, False, False]          # magnets enabled at start
    srv_mod = _server_module(monkeypatch, tmp_path)
    direct = EthernetRelayDirect(relay_ip="127.0.0.1", port=board.port)
    svc, bus, _ = make(present=True, relay=direct)
    tcp = srv_mod.InterlockTCPServer(svc, host="127.0.0.1", port=0)
    tcp.start()

    def no_direct():
        raise AssertionError("the client went around the server")
    try:
        assert svc.get_snapshot()["magnets_enabled"] is True   # startup read, preserved
        relay = EthernetRelay(client=_client_for(tcp._port), direct_factory=no_direct)
        relay.JOB_POLL_S = 0.05
        relay.source_on()
        assert board.states[2] is True
        assert relay.read_relay_status() == board.states
        relay.kill_magnets()
        assert board.states[1] is False
        relay.toggle_artiq_main_power(t_wait=0.1)
        assert board.states[0] is False
        assert any(c[1] == 48 and c[2] == 0 for c in board.commands)   # main was cut
        relay.source_off()
        assert board.states == [False, False, False, False]
        stats = svc.get_snapshot()["relay"]["stats"]
        assert stats["contacts"] >= 6 and stats["refused"] == 0 and stats["timeout"] == 0
    finally:
        tcp.stop()
        board.close()


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
