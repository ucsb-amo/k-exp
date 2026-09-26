"""Read-only telemetry for the Device Control GUI's Composite tab (K machine).

Each provider binds exactly one read call of its server's client and never
anything else: the Keysight and interlock servers' ``get_snapshot`` and
liveOD's side-effect-free ``POLL``.  Nothing here can switch a supply, reset
the interlock or touch a run.  No laser is read (the Precilaser and ALS stay
off the cards entirely).

Sources (``provider/key``):

* ``keysight/outer.*``, ``keysight/inner.*`` -- ``current_a``, ``output_on``,
  ``connected``; outer = the 500 A supply (.78), inner = the 170 A supply (.77).
* ``interlock/*`` -- ``state`` (ok | tripped | warmup | safe_mode | unknown),
  ``tripped``, ``magnets_enabled``, ``temperature_c``.
* ``live_od/*`` -- ``run_in_progress``, ``run_id``, ``expt_name``, ``n_shots``,
  ``n_shots_expected``, ``run_state``.
"""

from __future__ import annotations

import time

from waxx.util.device_state.telemetry import Sample, TelemetryProvider

#: Which coil each Keysight supply feeds (confirmed 2026-09-26: 500 A at .78
#: is the outer coil, 170 A at .77 the inner).
COIL_BY_SUPPLY_IP = {"192.168.1.78": "outer", "192.168.1.77": "inner"}

DISCOVERY_TIMEOUT_S = 0.5


def _age_from_epoch(t) -> float:
    """Age of an epoch timestamp from another machine; never negative (clock
    skew), so a skewed clock can only make a sample look older."""
    try:
        return max(time.time() - float(t), 0.)
    except (TypeError, ValueError):
        return 0.


class KeysightTelemetry(TelemetryProvider):
    name = "keysight"
    interval_s = 1.0

    def __init__(self):
        self._read = None

    def poll(self) -> dict[str, Sample]:
        if self._read is None:
            from waxx.util.guis.keysight.keysight_client import KeysightClient  # noqa: PLC0415
            self._read = KeysightClient(timeout_s=1.5,
                                        discovery_timeout=DISCOVERY_TIMEOUT_S).get_snapshot
        try:
            snapshot = self._read()
        except Exception:
            self._read = None           # rediscover next time
            raise
        out = {}
        for supply in snapshot or []:
            coil = COIL_BY_SUPPLY_IP.get(str(supply.get("ip", "")))
            if coil is None:
                continue
            age = _age_from_epoch(supply.get("t")) if supply.get("t") else 0.
            error = str(supply.get("error") or "")
            connected = bool(supply.get("connected"))
            current = supply.get("current_a")
            ok = connected and current is not None and not error
            out[f"{coil}.current_a"] = Sample(current, age, ok,
                                              error or ("" if connected else "not connected"))
            out[f"{coil}.output_on"] = Sample(supply.get("output_on"), age,
                                              connected and supply.get("output_on") is not None,
                                              error)
            out[f"{coil}.connected"] = Sample(connected, 0.)
        return out


class InterlockTelemetry(TelemetryProvider):
    name = "interlock"
    interval_s = 2.0

    def __init__(self):
        self._read = None

    def poll(self) -> dict[str, Sample]:
        if self._read is None:
            from kexp.util.guis.interlock.interlock_client import InterlockClient  # noqa: PLC0415
            self._read = InterlockClient(discovery_timeout=DISCOVERY_TIMEOUT_S,
                                         timeout=1.5).get_snapshot
        try:
            snap = self._read()
        except Exception:
            self._read = None
            raise
        if not isinstance(snap, dict) or snap.get("status") == "error":
            raise RuntimeError(f"interlock snapshot: {snap.get('message') if isinstance(snap, dict) else snap!r}")
        state = str(snap.get("state", "unknown"))
        out = {
            "state": Sample(state),
            "tripped": Sample(state == "tripped" or bool(snap.get("plc_tripped"))),
            "temperature_c": Sample(snap.get("temperature_c"), 0.,
                                    snap.get("temperature_c") is not None),
        }
        enabled = snap.get("magnets_enabled")
        age = snap.get("magnets_status_age_s")
        out["magnets_enabled"] = Sample(enabled, float(age) if age is not None else 0.,
                                        enabled is not None)
        return out


class LiveODTelemetry(TelemetryProvider):
    name = "live_od"
    interval_s = 2.0

    def __init__(self):
        self._read = None

    def poll(self) -> dict[str, Sample]:
        if self._read is None:
            from waxx.util.live_od.live_od_client import LiveODClient  # noqa: PLC0415
            self._read = LiveODClient(timeout_ms=1500,
                                      discovery_timeout=DISCOVERY_TIMEOUT_S).poll
        try:
            reply = self._read()
        except Exception:
            self._read = None
            raise
        if not isinstance(reply, dict) or not reply.get("ok", False):
            raise RuntimeError(f"liveOD POLL: {reply!r}")
        keys = ("run_in_progress", "run_id", "expt_name", "n_shots", "n_shots_expected",
                "run_state", "last_shot_age_s")
        return {k: Sample(reply.get(k)) for k in keys}


def default_providers() -> list[TelemetryProvider]:
    return [KeysightTelemetry(), InterlockTelemetry(), LiveODTelemetry()]
