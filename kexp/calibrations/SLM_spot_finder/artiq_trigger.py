"""The Andor's trigger line, pulsed from ARTIQ for the spot finder.

``make_andor_trigger()`` is a ``waxx.control.artiq.ttl_pulser.TTLPulser`` on
the TTL wired to the Andor's trigger input -- the same line a run uses
(``cameras.andor.trigger_ttl`` -> ``ttl.andor``, ``kexp.config``), with the
run's pulse length (``t_camera_trigger``).  One precompiled
``core.reset(); ttl.pulse(t)`` kernel, fired once per frame while the spot
finder's camera is armed for external triggers (served_source, triggered
mode).

Everything kexp is imported when this is called, not when the module is: the
spot finder GUI must open without artiq (as it does for its readout params).
"""

import os

from waxx.control.artiq.ttl_pulser import TTLPulser, T_LEAD_DEFAULT

#: How the pulser names itself to the monitor server: the fence's reason while
#: it holds the core, the untrusted-state reason, its end state's run name.
ANDOR_TRIGGER_LABEL = "SLM spot finder (ARTIQ trigger)"


def device_db_path() -> str:
    """The device database the lab runs with: env var ``db`` (what ``ar``
    passes), else kexp's own copy."""
    path = os.getenv("db")
    if path and os.path.isfile(path):
        return path
    from kexp.util.db import device_db as module
    return os.path.abspath(module.__file__)


def andor_trigger_spec() -> dict:
    """The Andor's trigger line from kexp's tables: ``ttl_name`` (device-db
    name, e.g. ``ttl7``), ``ttl_attr`` (ttl_frame attribute, e.g. ``andor``),
    ``channel``, ``t_pulse`` (the run's ``t_camera_trigger``) and
    ``exposure_delay``.  Raises with the reason when the tables cannot be read
    or name no trigger line."""
    from kexp.config.camera_id import camera_frame
    from kexp.config.ttl_id import ttl_frame
    params = camera_frame().andor
    attr = str(getattr(params, "trigger_ttl", "") or "")
    if not attr:
        raise RuntimeError("cameras.andor names no trigger_ttl in kexp.config.camera_id")
    ttl = getattr(ttl_frame(), attr, None)
    if ttl is None or not hasattr(ttl, "ch"):
        raise RuntimeError(f"ttl_frame has no TTL named {attr!r} (cameras.andor.trigger_ttl)")
    return {"ttl_name": str(ttl.name), "ttl_attr": attr, "channel": int(ttl.ch),
            "t_pulse": float(params.t_camera_trigger),
            "exposure_delay": float(getattr(params, "exposure_delay", 0.0) or 0.0)}


def make_andor_trigger(run_check=None, t_lead: float = T_LEAD_DEFAULT) -> TTLPulser:
    """A TTLPulser on the Andor's trigger line.  ``run_check`` is asked at
    release whether a run is in progress (the spot finder passes its liveOD
    run gate); see TTLPulser for what the pulser does around the monitor."""
    spec = andor_trigger_spec()
    return TTLPulser(spec["ttl_name"], device_db_path=device_db_path(),
                     t_pulse=spec["t_pulse"], t_lead=t_lead, label=ANDOR_TRIGGER_LABEL,
                     ttl_state_name=spec["ttl_attr"], run_check=run_check)


__all__ = ["make_andor_trigger", "andor_trigger_spec", "device_db_path",
           "ANDOR_TRIGGER_LABEL"]
