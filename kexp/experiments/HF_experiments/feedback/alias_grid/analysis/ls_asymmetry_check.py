"""Is the adaptive loop's offset asymmetry the light-shift term? Replay with the stored
frequency_lightshift varied (read-only; existing runs; nothing written).

    python ls_asymmetry_check.py <ALT2 rid> <NAALT2 rid>

For each light-shift value the recorded APD voltages and drives are re-scored (gap-aware replay on the
run's own grid): production hit for negative / positive initial offsets, overall hit, and the posterior
centroid within +/-0.3 Omega on a fine grid. If the asymmetry closes at some LS value for the adaptive run
while the non-adaptive run stays flat, the stored LS (42.9 kHz #85411) is the suspect.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
LS_KHZ = [20.0, 30.0, 36.8, 42.9, 48.3, 55.0, 65.0]


def score(fr, ls_hz):
    fr.p.frequency_lightshift = float(ls_hz)
    res = fr.replay_measured()
    P = np.asarray(res.P0_rr, float)[:, -1, :]
    n = P.shape[0]
    off = fr._resolve_fractional_initial_offset_r(n_repeat=n)
    z = np.array([fr._grid_for_offset(float(o))[1] for o in off])
    grids = np.array([fr._grid_for_offset(float(o))[0] for o in off])
    det = (grids - fr._omega_resonance_rad_s) / fr.Omega
    hit = (np.argmax(P, 1) == z)
    cen = []
    for r in range(n):
        w = np.abs(det[r]) <= 0.35
        if w.any() and P[r, w].sum() > 0:
            cen.append(np.sum(P[r, w] * det[r, w]) / P[r, w].sum())
    f_Om = fr.Omega / (2 * np.pi)
    return dict(ls_kHz=ls_hz / 1e3, hit=float(hit.mean()), hit_neg=float(hit[off < -1e-9].mean()), hit_pos=float(hit[off > 1e-9].mean()),
                centroid_kHz=float(np.mean(cen)) * f_Om / 1e3)


def main(rids):
    from kexp import atomdata
    from alias_replay_gaps import FeedbackReplayGaps
    out = {}
    for rid in rids:
        ad = atomdata(rid, roi_id="auto", lite=False)
        fr = FeedbackReplayGaps(ad)
        adaptive = int(np.ravel(ad.p.update_raman_frequency_bool)[0])
        print(f"run {rid} ({'adaptive' if adaptive else 'non-adaptive'}), stored LS {float(np.ravel(ad.p.frequency_lightshift)[0])/1e3:.2f} kHz")
        print(f"  {'LS kHz':>7} {'hit':>6} {'hit_neg':>8} {'hit_pos':>8} {'centroid kHz':>13}")
        rows = []
        for ls in LS_KHZ:
            r = score(fr, ls * 1e3); rows.append(r)
            print(f"  {r['ls_kHz']:7.1f} {r['hit']:6.3f} {r['hit_neg']:8.3f} {r['hit_pos']:8.3f} {r['centroid_kHz']:13.2f}", flush=True)
        out[rid] = rows
    json.dump(out, open(os.path.join(HERE, "ls_asymmetry_check.json"), "w"), indent=1)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
