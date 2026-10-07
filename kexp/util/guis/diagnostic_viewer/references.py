"""Saved references for the diagnostic viewer: one CSV row per reference, the
newest first when read (the magnetometer GUI's scheme).

A reference holds, per frame key, the mean and standard deviation of the
per-shot mean counts over the last ``window`` frames of that key, how many
frames that was, the exposure / gain they were taken with and their size in
pixels -- a frame is only ever compared with a reference taken at the same
settings, and a total count only with one of the same frame size (the total
of the reference is its mean times its pixel count: exact, the size being
fixed). Frames older than the newest change of settings or size are left
out, and the reference records how many were.
"""
from __future__ import annotations

import csv
import math
import os
import tempfile
import time
from datetime import datetime

from .frames import FRAME_KEYS, FrameHistory, same_settings

FIELDS = ("mean", "std", "n", "exposure", "gain", "n_pixels", "n_saturated_shots", "n_excluded")
HEAD = ("datetime_iso", "timestamp_s", "window", "runs", "note")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def build_reference(history: FrameHistory, window: int, note: str = "", now: float = None):
    """A reference from the last ``window`` frames of each key in ``history``,
    and a list of what was left out (human-readable). None when no key has a
    frame."""
    now = time.time() if now is None else float(now)
    ref = {"datetime_iso": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
           "timestamp_s": now, "window": int(window), "note": str(note), "keys": {}}
    notes, runs = [], set()
    for key in FRAME_KEYS:
        recent = history.last_n(key, window)
        if not recent:
            ref["keys"][key] = {f: math.nan for f in FIELDS} | {"n": 0, "n_excluded": 0}
            continue
        newest = recent[-1]
        used = []
        for e in reversed(recent):
            if not same_settings(e.exposure, e.gain, newest.exposure, newest.gain)                     or e.n_pixels != newest.n_pixels:
                break
            used.append(e)
        if not used:        # newest frame's settings not recorded: nothing comparable
            ref["keys"][key] = {f: math.nan for f in FIELDS} | {"n": 0, "n_excluded": len(recent)}
            notes.append(f"{key}: exposure/gain not recorded, no reference")
            continue
        used.reverse()
        n = len(used)
        vals = [e.mean for e in used]
        mean = sum(vals) / n
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else math.nan
        sat = [e.n_saturated for e in used]
        n_sat = math.nan if any(s is None for s in sat) else sum(1 for s in sat if s > 0)
        excluded = len(recent) - n
        if excluded:
            notes.append(f"{key}: {excluded} older frame(s) at other settings or frame size "
                         f"left out")
        if n < window:
            notes.append(f"{key}: {n} frame(s), fewer than the window of {window}")
        if isinstance(n_sat, int) and n_sat:
            notes.append(f"{key}: {n_sat} of {n} frames have saturated pixels")
        runs.update(e.run_id for e in used)
        ref["keys"][key] = {"mean": mean, "std": std, "n": n, "exposure": newest.exposure,
                            "gain": newest.gain, "n_pixels": newest.n_pixels,
                            "n_saturated_shots": n_sat, "n_excluded": excluded}
    if not runs:
        return None, ["no frames seen yet"]
    ref["runs"] = f"{min(runs)}-{max(runs)}" if len(runs) > 1 else str(min(runs))
    return ref, notes


def reference_stat(key_ref, stat):
    """(mean, std) of the reference in ``stat`` ("mean" or "total"), or None
    when it has no total (saved without its frame size)."""
    m, s = key_ref["mean"], key_ref["std"]
    if stat != "total":
        return m, s
    n = key_ref.get("n_pixels")
    if not isinstance(n, (int, float)) or not math.isfinite(n) or n <= 0:
        return None
    return m * n, s * n


def compare(value, exposure, gain, key_ref, stat="mean", n_pixels=None):
    """``value`` (a shot's or run's ``stat`` count, DN) against one key of a
    reference: ``{"delta_frac", "z"}``, or ``{"reason"}`` when they cannot be
    compared."""
    if not key_ref or not key_ref.get("n"):
        return {"reason": "no reference for this frame"}
    if not same_settings(exposure, gain, key_ref["exposure"], key_ref["gain"]):
        return {"reason": "settings differ from the reference"}
    ref_n = key_ref.get("n_pixels")
    if n_pixels is not None and isinstance(ref_n, (int, float)) and math.isfinite(ref_n)             and int(ref_n) != int(n_pixels):
        return {"reason": "frame size differs from the reference"}
    ms = reference_stat(key_ref, stat)
    if ms is None:
        return {"reason": "the reference has no frame size, so no total"}
    m, s = ms
    out = {"delta_frac": (value - m) / m if m else math.nan}
    out["z"] = (value - m) / s if (isinstance(s, float) and math.isfinite(s) and s > 0) else math.nan
    return out


class ReferenceStore:
    """The references CSV at ``path`` (None: references are not kept)."""

    def __init__(self, path):
        self.path = path

    def load(self):
        """All valid references, newest first. Raises FileNotFoundError when
        the file does not exist yet."""
        if not self.path:
            raise RuntimeError("reference CSV path is not configured")
        refs = []
        with open(self.path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts = _num(row.get("timestamp_s"))
                if not math.isfinite(ts):
                    continue
                window = _num(row.get("window"))
                ref = {"datetime_iso": row.get("datetime_iso", ""), "timestamp_s": ts,
                       "window": int(window) if math.isfinite(window) else 0,
                       "runs": row.get("runs", ""), "note": row.get("note", ""), "keys": {}}
                for key in FRAME_KEYS:
                    vals = {f: _num(row.get(f"{key}__{f}")) for f in FIELDS}
                    vals["n"] = int(vals["n"]) if math.isfinite(vals["n"]) else 0
                    ref["keys"][key] = vals
                refs.append(ref)
        refs.sort(key=lambda r: r["timestamp_s"], reverse=True)
        return refs

    def append(self, ref):
        try:
            refs = self.load()
        except FileNotFoundError:
            refs = []
        self.write([ref] + refs)

    def delete(self, timestamp_s):
        refs = [r for r in self.load() if r["timestamp_s"] != float(timestamp_s)]
        self.write(refs)
        return refs

    def write(self, refs):
        """Replace the file with ``refs`` (oldest first on disk), atomically."""
        if not self.path:
            raise RuntimeError("reference CSV path is not configured")
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        fields = list(HEAD) + [f"{k}__{f}" for k in FRAME_KEYS for f in FIELDS]
        fd, tmp = tempfile.mkstemp(prefix=".diagnostic_reference_", suffix=".csv", dir=folder)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for ref in sorted(refs, key=lambda r: r["timestamp_s"]):
                    row = {h: ref.get(h, "") for h in HEAD}
                    for key in FRAME_KEYS:
                        kr = ref["keys"].get(key, {})
                        for fld in FIELDS:
                            v = kr.get(fld, math.nan)
                            row[f"{key}__{fld}"] = "" if (isinstance(v, float) and math.isnan(v)) else v
                    w.writerow(row)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


__all__ = ["build_reference", "compare", "reference_stat", "ReferenceStore", "FIELDS"]
