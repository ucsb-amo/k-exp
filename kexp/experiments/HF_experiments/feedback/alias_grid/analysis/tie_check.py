"""Is the pulse-0 resonance/mirror choice an exact numerical tie? (read-only; alias_<rid>.npz)

    python tie_check.py <rid> [<rid> ...]

After the first pulse from the pole the predicted s_z depends only on (drive - omega_j)^2, and the grid
is centred exactly on the drive, so hypothesis pairs drive +/- n steps have mathematically equal
posteriors; the kernel's argmax (strict '>' over ascending index) then keeps the FIRST index of a tie.
Per run, from the recorded kernel posterior after pulse 0 (data.probabilities row 1):
  tie_frac      fraction of shots whose two largest values are a mirror pair about the drive
  rel_diff      median |P_a - P_b| / P_a of that pair (0 = exact tie; ~1e-16..1e-12 = rounding)
  first_wins    fraction of tied shots where the MAP is the lower index of the pair
  higher_freq   fraction of tied shots where the MAP is the higher-frequency member
  mirror_pos / mirror_neg   fraction of shots (positive / negative initial offsets) whose pulse-0 MAP
                is the mirror of the resonance about the drive rather than the resonance
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def main(rids):
    print(f"{'run':>6} {'tie_frac':>8} {'rel_diff_med':>12} {'first_wins':>10} {'higher_freq':>11} {'mirror_pos':>10} {'mirror_neg':>10}")
    for rid in rids:
        d = dict(np.load(os.path.join(HERE, f"alias_{rid}.npz"), allow_pickle=True))
        P1 = d["P_kernel_all"][:, 1, :]
        det0 = d["det0"]; z0 = d["z0"]; off = d["offsets"]
        n, m = P1.shape
        ties, rel, first, higher, mir = [], [], [], [], []
        for r in range(n):
            order = np.argsort(P1[r])[::-1]
            a, b = int(order[0]), int(order[1])
            drive = float(off[r])                       # drive detuning (Omega) = the grid centre
            pair = abs((det0[r, a] - drive) + (det0[r, b] - drive)) < 1e-6 * max(abs(det0[r, a] - drive), 1e-9)
            amap = int(np.argmax(P1[r]))                # numpy argmax = first maximum, like the kernel
            is_mirror = (amap != z0[r]) and abs((det0[r, amap] - drive) + (det0[r, z0[r]] - drive)) < 1e-6
            mir.append((np.sign(drive), is_mirror))
            if pair:
                ties.append(1.0)
                rel.append(abs(P1[r, a] - P1[r, b]) / max(P1[r, a], 1e-300))
                lo = min(a, b)
                first.append(float(amap == lo))
                hi_f = a if det0[r, a] > det0[r, b] else b
                higher.append(float(amap == hi_f))
            else:
                ties.append(0.0)
        mir = np.array(mir)
        mp = float(mir[mir[:, 0] > 0, 1].mean()) if (mir[:, 0] > 0).any() else np.nan
        mn = float(mir[mir[:, 0] < 0, 1].mean()) if (mir[:, 0] < 0).any() else np.nan
        print(f"{rid:>6} {np.mean(ties):8.3f} {np.median(rel) if rel else np.nan:12.2e} {np.mean(first) if first else np.nan:10.3f} "
              f"{np.mean(higher) if higher else np.nan:11.3f} {mp:10.3f} {mn:10.3f}")


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]])
