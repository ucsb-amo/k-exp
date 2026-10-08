"""Did the true resonance drift away from the stored frequency_raman_transition overnight?

    python drift_check.py <rid> [<rid> ...]

Read-only; uses alias_<rid>.npz (gap-aware fine-grid replays). Per run:
  peak_kHz      detuning of the maximum of the shot-averaged 801-pt final posterior (kHz from the stored resonance)
  centroid_kHz  posterior-weighted mean detuning within +/-0.3 Omega of the stored resonance, averaged over shots
  map_med_kHz   median fine-grid MAP detuning over shots with |MAP| < 0.3 Omega, with its count
  hit_neg / hit_pos   production hit for shots with negative / positive initial offset (offset 0 excluded)
  fold_shift    phase of the folded comb peak (orders): a drifted resonance shifts the comb phase by delta*T
A resonance that drifted by d shows as peak/centroid/map_med ~ d in every run (same sign), growing with time;
an unchanged resonance shows values scattered around 0.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
STEP = 0.0125


def load(rid):
    d = dict(np.load(os.path.join(HERE, f"alias_{rid}.npz"), allow_pickle=True))
    return {k: (v.item() if isinstance(v, np.ndarray) and v.ndim == 0 else v) for k, v in d.items()}


def main(rids):
    print(f"{'run':>6} {'f_Rabi':>7} {'peak_kHz':>9} {'centroid_kHz':>12} {'map_med_kHz (n)':>16} {'hit_neg':>8} {'hit_pos':>8} {'fold_shift':>10}")
    rows = []
    for rid in rids:
        d = load(rid)
        f_Om = d["Omega"] / (2 * np.pi)
        det2, Pw = d["det2"], d["P_wide_final"]
        # shot-averaged posterior on the common fine axis
        k = np.rint(det2 / STEP).astype(int); kmin = k.min(); n = k.max() - kmin + 1
        s = np.zeros(n); c = np.zeros(n)
        for r in range(Pw.shape[0]):
            s[k[r] - kmin] += Pw[r]; c[k[r] - kmin] += 1
        axis = (np.arange(n) + kmin) * STEP; m = np.where(c > 0, s / np.maximum(c, 1), 0)
        sel = np.abs(axis) <= 0.6
        peak = axis[sel][np.argmax(m[sel])] * f_Om / 1e3
        cen = []
        for r in range(Pw.shape[0]):
            w = np.abs(det2[r]) <= 0.3
            if w.sum() and Pw[r, w].sum() > 0:
                cen.append(np.sum(Pw[r, w] * det2[r, w]) / Pw[r, w].sum())
        centroid = float(np.mean(cen)) * f_Om / 1e3
        fmap = np.array([det2[r, np.argmax(Pw[r])] for r in range(Pw.shape[0])])
        near = np.abs(fmap) < 0.3
        map_med = float(np.median(fmap[near])) * f_Om / 1e3 if near.any() else np.nan
        off = d["offsets"]; Pk, z0 = d["P_kernel_final"], d["z0"]
        hit = (np.argmax(Pk, 1) == z0)
        hneg = float(hit[off < -1e-9].mean()) if (off < -1e-9).any() else np.nan
        hpos = float(hit[off > 1e-9].mean()) if (off > 1e-9).any() else np.nan
        # folded comb phase at the long gap
        gaps = d["dT_mu_rr"][:, :-1] * 1e-9
        T = float(gaps[:, 1::2].mean()) if gaps.shape[1] > 1 else float(gaps.mean())
        u = det2 * f_Om * T; selu = np.abs(u) >= 0.5
        frac = (u[selu] + 0.5) % 1 - 0.5
        edges = np.linspace(-0.5, 0.5, 41); idx = np.clip(np.digitize(frac, edges) - 1, 0, 39)
        fm = np.bincount(idx, weights=Pw[selu], minlength=40) / np.maximum(np.bincount(idx, minlength=40), 1)
        fshift = float(0.5 * (edges[1:] + edges[:-1])[np.argmax(fm)])
        rows.append(dict(run_id=rid, f_rabi_kHz=f_Om / 1e3, peak_kHz=float(peak), centroid_kHz=centroid, map_med_kHz=map_med, n_near=int(near.sum()),
                         hit_neg=hneg, hit_pos=hpos, fold_shift_orders=fshift))
        print(f"{rid:>6} {f_Om/1e3:7.1f} {peak:9.2f} {centroid:12.2f} {map_med:9.2f} ({near.sum():3d}) {hneg:8.3f} {hpos:8.3f} {fshift:10.3f}")
    json.dump(rows, open(os.path.join(HERE, "drift_check.json"), "w"), indent=1)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
