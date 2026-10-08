"""Score a bimodality-rule run against a control ALT2 run of the same grid (read-only).

    python bimodal_check.py <bimodal rid> [<control rid> ...]

Bimodal run: per pulse, the fraction of shots where the rule fired (data.drive_rule), the median
second-mode ratio (data.bimodal_ratio); then for every run given: production hit and fine MAP within
+/-0.04 Omega by initial-offset sign, the mean signed drive detuning per pulse (grid steps, frequency
sign) by offset sign, and the gap-aware replay agreement. Each run is replayed with alias_replay.py if
its alias_<rid>.npz is missing.
"""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HALF_WIN = 0.04


def ensure_npz(rid):
    path = os.path.join(HERE, f"alias_{rid}.npz")
    if not os.path.exists(path):
        subprocess.run([sys.executable, os.path.join(HERE, "alias_replay.py"), str(rid)], check=True)
    d = dict(np.load(path, allow_pickle=True))
    return {k: (v.item() if isinstance(v, np.ndarray) and v.ndim == 0 else v) for k, v in d.items()}


def by_sign(d):
    off = d["offsets"]; z0 = d["z0"]; Pk = d["P_kernel_final"]; det2, Pw = d["det2"], d["P_wide_final"]
    om = d["omega_rr"]; Omega = d["Omega"]; f_res = d["f_res"]
    step = float(np.abs(np.diff(d["det0"][0])).mean())
    hit = (np.argmax(Pk, 1) == z0).astype(float)
    fmap = np.array([det2[r, np.argmax(Pw[r])] for r in range(Pw.shape[0])])
    near = (np.abs(fmap) <= HALF_WIN).astype(float)
    drive = (om - 2 * np.pi * f_res) / Omega / step
    out = {}
    for name, sel in (("neg", off < -1e-9), ("pos", off > 1e-9)):
        n = int(sel.sum())
        out[name] = dict(n=n, hit=float(hit[sel].mean()), hit_sem=float(np.sqrt(hit[sel].mean() * (1 - hit[sel].mean()) / n)),
                         fine_near=float(near[sel].mean()), drive_mean_steps=[round(float(x), 2) for x in drive[sel].mean(0)])
    out["all"] = dict(hit=float(hit.mean()), fine_near=float(near.mean()), n=int(hit.size))
    return out


def main(rids):
    from kexp import atomdata
    rid0 = rids[0]
    ad = atomdata(rid0, roi_id="auto", lite=False)
    n_p = int(np.ravel(ad.p.N_pulses)[0])
    rule = np.asarray(ad.data.drive_rule, float).reshape(-1, n_p)
    ratio = np.asarray(ad.data.bimodal_ratio, float).reshape(-1, n_p)
    print(f"bimodal run {rid0}: {rule.shape[0]} shots, {n_p} pulses, ratio threshold {float(np.ravel(ad.p.bimodal_mode_ratio)[0])}, "
          f"min separation {int(np.ravel(ad.p.bimodal_min_separation)[0])}")
    print("  rule fired (fraction of shots) by pulse: " + " ".join(f"{x:.2f}" for x in rule.mean(0)))
    print("  median second-mode ratio by pulse:      " + " ".join(f"{x:.2f}" for x in np.median(ratio, 0)))
    print(f"  shots where the rule fired at least once: {float((rule.sum(1) > 0).mean()):.2f}")
    res = {}
    for rid in rids:
        d = ensure_npz(rid)
        s = by_sign(d)
        res[rid] = s
        tag = "BIMODAL" if rid == rid0 else "control"
        print(f"{tag} {rid}: hit {s['all']['hit']:.3f} fine_near {s['all']['fine_near']:.3f} | neg: hit {s['neg']['hit']:.3f}±{s['neg']['hit_sem']:.3f} "
              f"fine {s['neg']['fine_near']:.3f} | pos: hit {s['pos']['hit']:.3f}±{s['pos']['hit_sem']:.3f} fine {s['pos']['fine_near']:.3f} | "
              f"replay max|dP| {d['max_dP_kernel_vs_replay']:.1e} MAP {d['map_agree']:.3f}")
        print(f"    drive-res by pulse, neg offsets: " + " ".join(f"{x:+.2f}" for x in s["neg"]["drive_mean_steps"]))
        print(f"    drive-res by pulse, pos offsets: " + " ".join(f"{x:+.2f}" for x in s["pos"]["drive_mean_steps"]))
    json.dump(dict(bimodal=rid0, rule_by_pulse=rule.mean(0).tolist(), ratio_median_by_pulse=np.median(ratio, 0).tolist(), runs=res),
              open(os.path.join(HERE, f"bimodal_check_{rid0}.json"), "w"), indent=1)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
