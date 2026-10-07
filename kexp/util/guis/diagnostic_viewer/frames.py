"""What the diagnostic viewer shows, and the numbers it computes from a frame.

No Qt here: the per-frame statistics, the per-run tally and the history the
reference is built from are plain Python, so they can be tested alone.

A frame's numbers are taken over the frame exactly as the run stores it (the
DiagnosticCamera ROI, block-averaged when the camera has none), in camera
counts (DN), with nothing subtracted. Each frame's ``<key>_meta`` record says
what it was taken with; a record whose ``seq`` is NaN is a cleared slot (a
warm-up / repeated shot starting over), not a frame, and is never counted.
"""
from __future__ import annotations

import collections
import math
from dataclasses import dataclass

import numpy as np

from waxa.data.camera_frames import META_FIELDS


@dataclass(frozen=True)
class FrameSpec:
    key: str        # DataVault key (kexp.config.camera_id.diagnostic_cameras)
    label: str
    camera: str
    image: bool     # shown as an image (else: counts only)


FRAMES = (
    FrameSpec("img_mot", "MOT fluorescence", "MOT basler", True),
    FrameSpec("img_gm", "GM fluorescence", "MOT basler", True),
    FrameSpec("img_2dmot", "2D MOT fluorescence", "2D-MOT basler", True),
    FrameSpec("img_mot_beams_xy", "MOT beams", "xy basler", False),
    FrameSpec("img_gm_beams_xy", "GM beams", "xy basler", False),
    FrameSpec("img_mot_beams_z", "MOT beams", "z basler", False),
    FrameSpec("img_gm_beams_z", "GM beams", "z basler", False),
)
FRAME_KEYS = tuple(f.key for f in FRAMES)
SPEC = {f.key: f for f in FRAMES}

_I_SEQ = META_FIELDS.index("seq")
_I_EXPOSURE = META_FIELDS.index("exposure")
_I_GAIN = META_FIELDS.index("gain")


def configured_keys():
    """The frame keys kexp's diagnostic_cameras takes per shot, or None when
    the config cannot be imported here (then nothing is marked unconfigured)."""
    try:
        from kexp.config.camera_id import diagnostic_cameras  # noqa: PLC0415
    except Exception:
        return None
    keys = set()
    for entry in diagnostic_cameras.entries():
        keys.update(entry.frames)
    return keys


def saturation_level(dtype):
    """The count a saturated pixel reads, or None when the dtype does not say
    (a uint16 frame may be 10, 12 or 16 bit: not checked)."""
    return 255 if np.dtype(dtype) == np.uint8 else None


@dataclass
class FrameStats:
    run_id: int
    index: tuple            # the shot's slot in the run file (unshuffled)
    t: float                # when liveOD took it (s since epoch)
    mean: float             # DN over the stored frame
    total: float            # DN summed over the stored frame
    max: float
    n_pixels: int
    n_saturated: int | None  # None: not checked for this dtype
    exposure: float          # s, as the frame was taken (NaN = not recorded)
    gain: float              # dB
    seq: float


def frame_stats(img, meta, run_id, index, t):
    """FrameStats for one pushed frame, or None when it is not a frame: a
    placeholder (one byte per shot), or a cleared slot (``seq`` NaN)."""
    a = np.asarray(img)
    if a.ndim < 2 or a.size <= 1:
        return None
    seq = exposure = gain = math.nan
    if meta is not None:
        m = np.asarray(meta, dtype=np.float64).ravel()
        if m.size == len(META_FIELDS):
            seq, exposure, gain = float(m[_I_SEQ]), float(m[_I_EXPOSURE]), float(m[_I_GAIN])
        if not math.isfinite(seq):
            return None
    sat = saturation_level(a.dtype)
    return FrameStats(
        run_id=int(run_id), index=tuple(int(i) for i in (index or ())), t=float(t),
        mean=float(a.mean(dtype=np.float64)), total=float(a.sum(dtype=np.float64)),
        max=float(a.max()), n_pixels=int(a.size),
        n_saturated=None if sat is None else int(np.count_nonzero(a >= sat)),
        exposure=exposure, gain=gain, seq=seq)


STATS = ("total", "mean")       # what a row shows; the first is the default


def stat_value(st: "FrameStats", stat):
    """A frame's total or mean count (DN)."""
    return st.total if stat == "total" else st.mean


def same_settings(exp_a, gain_a, exp_b, gain_b):
    """Two frames were taken with the same exposure and gain. An unrecorded
    (NaN) value matches nothing, so such a frame is never compared. Values are
    the camera's read-back (3 dB reads 2.999994): equal to 0.1 % in exposure
    and 0.01 dB in gain."""
    vals = (exp_a, gain_a, exp_b, gain_b)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
        return False
    return math.isclose(exp_a, exp_b, rel_tol=1e-3, abs_tol=1e-9) and \
        math.isclose(gain_a, gain_b, rel_tol=0.0, abs_tol=0.01)


def mean_sem(values):
    """(mean, standard error, n) of ``values``; sem NaN for n < 2."""
    v = np.asarray(list(values), dtype=np.float64)
    n = int(v.size)
    if n == 0:
        return math.nan, math.nan, 0
    if n == 1:
        return float(v[0]), math.nan, 1
    return float(v.mean()), float(v.std(ddof=1) / math.sqrt(n)), n


class FrameHistory:
    """Every frame the viewer has seen, per key, newest last (bounded). One
    entry per (run, slot): a slot that comes again (a repeated shot) replaces
    the earlier one rather than counting twice."""

    def __init__(self, maxlen=5000):
        self._by_key = {k: collections.OrderedDict() for k in FRAME_KEYS}
        self._maxlen = int(maxlen)

    def add(self, key, st: FrameStats):
        d = self._by_key.setdefault(key, collections.OrderedDict())
        slot = (st.run_id, st.index)
        d.pop(slot, None)
        d[slot] = st
        while len(d) > self._maxlen:
            d.popitem(last=False)

    def latest(self, key):
        d = self._by_key.get(key)
        return next(reversed(d.values())) if d else None

    def entries(self, key):
        return list(self._by_key.get(key, {}).values())

    def run_entries(self, key, run_id):
        return [s for s in self.entries(key) if s.run_id == run_id]

    def last_n(self, key, n):
        e = self.entries(key)
        return e[-int(n):] if n > 0 else []

    def clear(self):
        for d in self._by_key.values():
            d.clear()


def run_summary(history: FrameHistory, key, run_id, stat="mean"):
    """Mean +- sem over the shots of run ``run_id`` of each shot's ``stat`` of
    ``key`` (STATS), over the frames taken with the run's latest settings and
    frame size (a run where they changed part-way says so in
    ``n_other_settings``)."""
    entries = history.run_entries(key, run_id)
    if not entries:
        return None
    last = entries[-1]
    same = [e for e in entries if same_settings(e.exposure, e.gain, last.exposure, last.gain)
            and e.n_pixels == last.n_pixels]
    if not same:            # settings not recorded: report them all, unlabelled
        same = entries
    mean, sem, n = mean_sem(stat_value(e, stat) for e in same)
    sat = [e.n_saturated for e in same]
    return {"mean": mean, "sem": sem, "n": n, "n_other_settings": len(entries) - len(same),
            "exposure": last.exposure, "gain": last.gain, "n_pixels": last.n_pixels,
            "n_shots_saturated": None if any(s is None for s in sat)
            else sum(1 for s in sat if s > 0)}


__all__ = ["FrameSpec", "FRAMES", "FRAME_KEYS", "SPEC", "configured_keys", "saturation_level",
           "FrameStats", "frame_stats", "STATS", "stat_value", "same_settings", "mean_sem", "FrameHistory", "run_summary"]
