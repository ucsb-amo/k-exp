"""Device Control telemetry providers close a client before dropping it after a
failed read (liveOD's client holds a zmq context + IO thread; dropping it
unclosed every 2 s while liveOD is unreachable churned contexts).  Fakes only;
nothing goes on the network."""
import pytest

from kexp.util.guis.device_state_gui import telemetry_providers as tp


class OnlyReads:
    """A client whose only allowed call is ``read_name`` (anything else
    fails the test)."""

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


class Closable(OnlyReads):
    def close(self):
        self.calls.append("close")


def test_a_dropped_client_is_closed_first(monkeypatch):
    made = []
    import waxx.util.live_od.live_od_client as lc

    def make(*a, **k):
        c = Closable("poll", ConnectionError("gone"))
        made.append(c)
        return c
    monkeypatch.setattr(lc, "LiveODClient", make)
    p = tp.LiveODTelemetry()
    for _ in range(3):
        with pytest.raises(ConnectionError):
            p.poll()
    assert [c.calls for c in made] == [["poll", "close"]] * 3


def test_a_good_client_is_kept_and_not_closed(monkeypatch):
    import waxx.util.live_od.live_od_client as lc
    c = Closable("poll", {"ok": True, "run_in_progress": False})
    monkeypatch.setattr(lc, "LiveODClient", lambda *a, **k: c)
    p = tp.LiveODTelemetry()
    for _ in range(3):
        p.poll()
    assert c.calls == ["poll"] * 3


def test_a_client_without_close_is_just_dropped(monkeypatch):
    import waxx.util.guis.keysight.keysight_client as kc
    client = OnlyReads("get_snapshot", ConnectionError("gone"))
    monkeypatch.setattr(kc, "KeysightClient", lambda *a, **k: client)
    p = tp.KeysightTelemetry()
    with pytest.raises(ConnectionError):
        p.poll()
    assert client.calls == ["get_snapshot"] and p._read is None
