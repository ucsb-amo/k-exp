"""The Device Control GUI's telemetry providers (kexp): which supply is which
coil, and that each provider only ever calls its one read method.  The
clients are fakes; nothing goes on the network."""
import time

import pytest

from kexp.util.guis.device_state_gui import telemetry_providers as tp


class OnlyReads:
    """A client whose only allowed call is ``read_name``; touching anything
    else (turn_on, reset_interlock, ...) fails the test."""

    def __init__(self, read_name, reply):
        object.__setattr__(self, "_read_name", read_name)
        object.__setattr__(self, "_reply", reply)
        object.__setattr__(self, "calls", [])

    def __getattr__(self, name):
        if name != self._read_name:
            raise AssertionError(f"provider touched {name!r}")

        def read():
            self.calls.append(name)
            if isinstance(self._reply, Exception):
                raise self._reply
            return self._reply
        return read


def test_keysight_mapping_matches_the_lab_config():
    from kexp.config.ip import KEYSIGHT_SUPPLIES
    by_max = {max_i: ip for max_i, ip in KEYSIGHT_SUPPLIES}
    assert tp.COIL_BY_SUPPLY_IP[by_max[500]] == "outer"
    assert tp.COIL_BY_SUPPLY_IP[by_max[170]] == "inner"


def test_keysight_provider(monkeypatch):
    now = time.time()
    snapshot = [
        {"ip": "192.168.1.78", "max_current": 500, "connected": True, "output_on": True,
         "current_a": 188.4, "status": 0, "error": None, "t": now - 0.5, "seq": 3},
        {"ip": "192.168.1.77", "max_current": 170, "connected": False, "output_on": None,
         "current_a": None, "status": 0, "error": None, "t": None, "seq": 0},
    ]
    client = OnlyReads("get_snapshot", snapshot)
    import waxx.util.guis.keysight.keysight_client as kc
    monkeypatch.setattr(kc, "KeysightClient", lambda *a, **k: client)
    got = tp.KeysightTelemetry().poll()
    assert got["outer.current_a"].value == 188.4 and got["outer.current_a"].ok
    assert got["outer.current_a"].age_s == pytest.approx(0.5, abs=0.3)
    assert got["outer.output_on"].value is True
    assert not got["inner.current_a"].ok and "not connected" in got["inner.current_a"].error
    assert client.calls == ["get_snapshot"]


def test_interlock_provider(monkeypatch):
    client = OnlyReads("get_snapshot", {"state": "tripped", "plc_tripped": True,
                                        "magnets_enabled": False, "magnets_status_age_s": 1.2,
                                        "temperature_c": 22.0})
    import kexp.util.guis.interlock.interlock_client as ic
    monkeypatch.setattr(ic, "InterlockClient", lambda *a, **k: client)
    got = tp.InterlockTelemetry().poll()
    assert got["state"].value == "tripped" and got["tripped"].value is True
    assert got["magnets_enabled"].value is False and got["magnets_enabled"].age_s == 1.2
    assert client.calls == ["get_snapshot"]


def test_live_od_provider_only_polls(monkeypatch):
    client = OnlyReads("poll", {"ok": True, "run_in_progress": True, "run_id": 81234,
                                "expt_name": "rabi", "n_shots": 3, "n_shots_expected": 40})
    import waxx.util.live_od.live_od_client as lc
    monkeypatch.setattr(lc, "LiveODClient", lambda *a, **k: client)
    got = tp.LiveODTelemetry().poll()
    assert got["run_in_progress"].value is True and got["run_id"].value == 81234
    assert client.calls == ["poll"]


def test_a_failed_read_rediscovers_next_time(monkeypatch):
    made = []
    import waxx.util.guis.keysight.keysight_client as kc

    def make(*a, **k):
        made.append(1)
        return OnlyReads("get_snapshot", ConnectionError("gone"))
    monkeypatch.setattr(kc, "KeysightClient", make)
    p = tp.KeysightTelemetry()
    for _ in range(2):
        with pytest.raises(ConnectionError):
            p.poll()
    assert len(made) == 2
