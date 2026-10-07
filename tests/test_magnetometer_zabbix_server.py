"""The magnetometer -> Zabbix push server, offline.

The Zabbix transport is a fake and the field log is in tmp_path.  The TCP
server object is built but never started, so nothing binds and nothing
beacons.
"""
from __future__ import annotations

import datetime as _dt
import json
import struct
import time

from waxa.climate import ZabbixSender
from waxa.climate import magnetometer as mag
from waxa.climate.magnetometer import DEFAULT_KEYS, MagnetometerPusher

from kexp.util.dashboard import dashboard_hosts
from kexp.util.dashboard.server_registry import get_spec
from kexp.util.guis.zabbix.magnetometer_zabbix_server import (
    SERVER_ID, MagnetometerPushService, MagnetometerZabbixTCPServer,
)

HEADER = "datetime_iso,timestamp_s,Bx,By,Bz,Btot\n"


class FakeSender(ZabbixSender):
    def __init__(self, up=True, known_keys=tuple(DEFAULT_KEYS.values())):
        super().__init__("fake", 10051, timeout=0.1)
        self.up = up
        self.known_keys = known_keys
        self.entries: list[dict] = []

    def _exchange(self, packet: bytes) -> bytes:
        if not self.up:
            raise ConnectionError("down")
        (n, _) = struct.unpack("<II", packet[5:13])
        data = json.loads(packet[13:13 + n])["data"]
        good = [e for e in data if e["key"] in self.known_keys]
        self.entries += good
        return self.pack({"response": "success", "info":
                          f"processed: {len(good)}; failed: {len(data) - len(good)}; "
                          f"total: {len(data)}; seconds spent: 0.0"})


def _write(tmp_path, n, end=None):
    """n rows 1 s apart ending now, in today's file; Bx counts up from 0.001."""
    end = float(int(time.time())) if end is None else end
    path = mag.day_file(tmp_path, _dt.date.fromtimestamp(end))
    rows = "".join(f"x,{end - (n - 1 - i):.3f},{0.001 * (i + 1)},-0.2,0.3,0.36\n" for i in range(n))
    path.write_text(HEADER + rows)
    return end


def _service(tmp_path, sender, **kw):
    return MagnetometerPushService(MagnetometerPusher(sender, tmp_path, host="K", **kw), 60)


def test_filename_matches_the_magnetometer_server():
    from waxx.util.guis.HMR_magnetometer import hmr_magnetometer_server as srv
    assert mag.FIELD_LOG_FILENAME == srv.FIELD_LOG_FILENAME
    assert set(DEFAULT_KEYS) | {mag.TIME_COLUMN} <= set(srv.FIELD_LOG_FIELDS)


def test_first_push_sends_only_the_newest_reading_to_all_four_items(tmp_path):
    end = _write(tmp_path, 30)
    sender = FakeSender()
    svc = _service(tmp_path, sender)
    svc.push_once()
    assert {e["key"]: e["value"] for e in sender.entries} == {
        "k.magnetometer.bx": "0.03", "k.magnetometer.by": "-0.2",
        "k.magnetometer.bz": "0.3", "k.magnetometer.btot": "0.36"}
    assert {e["clock"] for e in sender.entries} == {int(end)}
    snap = svc.get_snapshot()
    assert snap["sent"] == 4 and snap["refused"] == 0 and snap["last_error"] == ""
    assert snap["field_g"]["Bx"] == 0.03 and snap["zabbix_reachable"] is True


def test_resume_sends_rows_as_written_one_per_spacing(tmp_path):
    end = _write(tmp_path, 30)
    sender = FakeSender()
    svc = _service(tmp_path, sender, resume_after=end - 30, min_interval_s=10.0)
    svc.push_once()
    bx = [float(e["value"]) for e in sender.entries if e["key"] == "k.magnetometer.bx"]
    assert bx == [0.001 * 10, 0.001 * 20, 0.001 * 30]   # rows 10, 20, 30 as written: no averaging


def test_unreachable_keeps_readings_and_recovers(tmp_path):
    _write(tmp_path, 3)
    sender = FakeSender(up=False)
    svc = _service(tmp_path, sender)
    svc.push_once()
    snap = svc.get_snapshot()
    assert snap["zabbix_reachable"] is False and snap["pending"] == 1 and snap["sent"] == 0
    sender.up = True
    svc.push_once()
    snap = svc.get_snapshot()
    assert snap["zabbix_reachable"] is True and snap["pending"] == 0 and snap["sent"] == 4


def test_missing_items_are_reported(tmp_path):
    _write(tmp_path, 3)
    svc = _service(tmp_path, FakeSender(known_keys=("k.magnetometer.btot",)))
    svc.push_once()
    snap = svc.get_snapshot()
    assert snap["sent"] == 1 and snap["refused"] == 3 and "refused" in snap["last_error"]


def test_dispatch_and_beacon_id(tmp_path):
    _write(tmp_path, 3)
    tcp = MagnetometerZabbixTCPServer(_service(tmp_path, FakeSender()))
    assert tcp.BEACON_ID == SERVER_ID == "zabbix_magnetometer"
    assert "k.magnetometer.btot" in json.loads(tcp.dispatch("get_snapshot"))["zabbix_key"]


def test_registered_and_autostarted_everywhere():
    spec = get_spec("zabbix_magnetometer")
    assert spec is not None and spec.hidden_panel and spec.server_id == SERVER_ID
    assert spec.server_cmd[-1] == "kexp.util.guis.zabbix.magnetometer_zabbix_server"
    assert "zabbix_magnetometer" in dashboard_hosts.HOST_AUTOSTART_SERVERS["*"]
