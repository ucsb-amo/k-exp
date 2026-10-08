"""Where does the adaptive loop end up from positive vs negative initial offsets? (read-only; alias_<rid>.npz)

    python asym_check.py <rid> [<rid> ...]

Per run: final kernel MAP bin relative to the resonant bin, histogrammed separately for negative and
positive initial offsets; the drive's detuning from resonance per pulse (median |drive - res| in grid
steps) for the two offset signs; and the first-pulse MAP jump (bin of the MAP after pulse 0 relative to
resonance) by offset sign.
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


def main(rids):
    for rid in rids:
        d = dict(np.load(os.path.join(HERE, f"alias_{rid}.npz"), allow_pickle=True))
        d = {k: (v.item() if isinstance(v, np.ndarray) and v.ndim == 0 else v) for k, v in d.items()}
        off = d["offsets"]; z0 = d["z0"]; Pk = d["P_kernel_all"]; det0 = d["det0"]; om = d["omega_rr"]
        Omega = d["Omega"]; f_res = d["f_res"]
        step = float(np.abs(np.diff(det0[0])).mean())
        n_shot, n_row, m = Pk.shape
        fin = np.argmax(Pk[:, -1, :], 1) - z0
        first = np.argmax(Pk[:, 1, :], 1) - z0
        drive_steps = (om - 2 * np.pi * f_res) / Omega / step          # drive detuning in grid steps, per pulse
        print(f"run {rid}: {n_shot} shots, {n_row-1} pulses, step {step:.3f} Omega")
        for name, sel in (("negative offsets", off < -1e-9), ("positive offsets", off > 1e-9)):
            vals, cnt = np.unique(fin[sel], return_counts=True)
            hist = ", ".join(f"{int(v):+d}:{int(c)}" for v, c in zip(vals, cnt))
            v1, c1 = np.unique(first[sel], return_counts=True)
            h1 = ", ".join(f"{int(v):+d}:{int(c)}" for v, c in zip(v1, c1))
            med = np.median(np.abs(drive_steps[sel]), axis=0)
            mean_signed = np.mean(drive_steps[sel], axis=0)
            print(f"  {name} (n={int(sel.sum())}): final MAP bin rel. to resonance -> {hist}")
            print(f"    MAP after pulse 0 -> {h1}")
            print(f"    median |drive-res| by pulse (steps): " + " ".join(f"{x:.2f}" for x in med))
            print(f"    mean signed drive-res by pulse (steps): " + " ".join(f"{x:+.2f}" for x in mean_signed))


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
