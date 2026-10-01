"""The coil -> Zabbix push server, offline.

The Zabbix transport is a fake and the history file is in tmp_path.  The TCP
server object is built but never started, so nothing binds and nothing
beacons.
"""
from __future__ import annotations

import datetime as _dt
import json
import struct
import time

from waxa.climate import ZabbixSender
from waxa.climate.coil import CoilTemperaturePusher

from kexp.util.dashboard import dashboard_hosts
from kexp.util.dashboard.server_registry import get_spec
from kexp.util.guis.zabbix.coil_zabbix_server import (
    SERVER_ID, CoilPushService, CoilZabbixTCPServer,
)

HEADER = "epoch,local_time,temperature_plc_k,temperature_c,flow1_v,flow2_v,flow3_v,flow4_v,plc_tripped\n"


class FakeSender(ZabbixSender):
    def __init__(self, up=True, accept=True):
        super().__init__("fake", 10051, timeout=0.1)
        self.up = up
        self.accept = accept
        self.values: list[str] = []

    def _exchange(self, packet: bytes) -> bytes:
        if not self.up:
            raise ConnectionError("down")
        (n, _) = struct.unpack("<II", packet[5:13])
        data = json.loads(packet[13:13 + n])["data"]
        ok = len(data) if self.accept else 0
        if self.accept:
            self.values += [e["value"] for e in data]
        return self.pack({"response": "success", "info":
                          f"processed: {ok}; failed: {len(data) - ok}; total: {len(data)}; seconds spent: 0.0"})


def _write(tmp_path, temps, start=None):
    """Rows ending now, 20 s apart, in today's file."""
    now = time.time() if start is None else start
    path = tmp_path / f"{_dt.date.fromtimestamp(now).isoformat()}.csv"
    rows = "".join(f"{now - 20 * (len(temps) - 1 - i):.3f},x,{t + 273.0:.5f},{t:.3f},5,6,5,7,0\n"
                   for i, t in enumerate(temps))
    path.write_text(HEADER + rows)


def _service(tmp_path, sender):
    return CoilPushService(CoilTemperaturePusher(sender, tmp_path, host="K"), interval_s=60)


def test_push_once_sends_and_reports(tmp_path):
    _write(tmp_path, [20.0, 21.0])
    sender = FakeSender()
    svc = _service(tmp_path, sender)
    svc.push_once()
    snap = svc.get_snapshot()
    assert sender.values == ["21.0"]
    assert snap["sent"] == 1 and snap["refused"] == 0 and snap["last_error"] == ""
    assert snap["temperature_c"] == 21.0 and snap["zabbix_reachable"] is True
    assert snap["last_success_age_s"] is not None


def test_unreachable_does_not_raise_and_recovers(tmp_path):
    _write(tmp_path, [20.0])
    sender = FakeSender(up=False)
    svc = _service(tmp_path, sender)
    svc.push_once()
    snap = svc.get_snapshot()
    assert snap["zabbix_reachable"] is False and snap["pending"] == 1 and snap["sent"] == 0
    sender.up = True
    svc.push_once()
    snap = svc.get_snapshot()
    assert snap["zabbix_reachable"] is True and snap["pending"] == 0 and sender.values == ["20.0"]


def test_refused_values_are_reported(tmp_path):
    _write(tmp_path, [20.0])
    svc = _service(tmp_path, FakeSender(accept=False))
    svc.push_once()
    snap = svc.get_snapshot()
    assert snap["refused"] == 1 and "refused" in snap["last_error"]
    assert snap["last_success_age_s"] is None


def test_dispatch(tmp_path):
    _write(tmp_path, [20.0])
    stopped = []
    tcp = CoilZabbixTCPServer(_service(tmp_path, FakeSender()),
                              on_shutdown_request=lambda: stopped.append(True))
    assert json.loads(tcp.dispatch("get_snapshot"))["zabbix_key"] == "k.coil.temperature"
    assert json.loads(tcp.dispatch("NOPE"))["status"] == "error"
    assert json.loads(tcp.dispatch("SHUTDOWN")) == {"status": "ok"}
    deadline = time.time() + 2.0
    while not stopped and time.time() < deadline:
        time.sleep(0.02)
    assert stopped == [True]


def test_registered_and_autostarted_everywhere():
    spec = get_spec("zabbix_coil")
    assert spec is not None and spec.hidden_panel and spec.server_id == SERVER_ID
    assert spec.server_cmd[-1] == "kexp.util.guis.zabbix.coil_zabbix_server"
    assert "zabbix_coil" in dashboard_hosts.HOST_AUTOSTART_SERVERS["*"]
