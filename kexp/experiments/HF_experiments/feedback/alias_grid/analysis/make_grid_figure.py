"""Figure: how the feedback hypothesis grid is built for a given initial offset, and why its step is set from T.

    python make_grid_figure.py

Panel A uses the overnight 2026-10-08 rule-grid numbers (t_pi 3.7892 us -> f_Rabi 131.95 kHz; 15 points; q = 2.4 on the
59.10 us nominal long gap -> step 40.606 kHz = 0.3077 Omega; measured mean gaps 44.6 / 60.0 us). Panel B is the synthetic
order sweep on the 85352 shots (order_sweep_85352.json; 21-pt grid, 17 pulses, stored noise, 5 x 105 shots per point).
Writes fig_grid_construction.png.
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
F_RABI = 131.95e3
M = 15
STEP = 0.30773                      # Omega
SPAN = STEP * (M - 1) / 2
T_LONG, T_SHORT = 60.0e-6, 44.6e-6  # measured mean gaps
A_LONG, A_SHORT = (1 / T_LONG) / F_RABI, (1 / T_SHORT) / F_RABI


def grid(offset_steps):
    """Kernel grid in Omega relative to resonance (descending), centre = initial drive, snapped onto resonance."""
    centre = offset_steps * STEP
    t = -1.0 + np.arange(M) * 2.0 / (M - 1)
    g = centre - SPAN * t
    j = int(np.argmin(np.abs(g)))
    return g - g[j], centre


def main():
    fig = plt.figure(figsize=(10, 7.4))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.45, 1], hspace=0.45, wspace=0.28)
    axA = fig.add_subplot(gs[0, :])
    rows = [(0, "initial offset 0"), (3, "initial offset +3 steps (+0.92 Ω)"), (-5, "initial offset −5 steps (−1.54 Ω)")]
    lim = 2.6
    for n in range(-25, 26):
        if n and abs(n * A_LONG) <= lim:
            axA.axvline(n * A_LONG, color="#eb6834", lw=0.9, alpha=0.28)
        if n and abs(n * A_SHORT) <= lim:
            axA.axvline(n * A_SHORT, color="#2a78d6", lw=0.9, alpha=0.3)
    axA.axvline(0, color="#008300", lw=1.4)
    for yi, (k, lab) in enumerate(rows):
        y = len(rows) - 1 - yi
        g, c = grid(k)
        inside = np.abs(g) <= lim
        axA.plot(g[inside], np.full(inside.sum(), y), "|", color="black", ms=16, mew=1.6)
        axA.plot([g.min(), g.max()], [y, y], color="black", lw=0.6, alpha=0.5)
        axA.plot(c, y, "v", color="#4a3aa7", ms=10, zorder=5)
        axA.text(-lim + 0.03, y + 0.28, lab, fontsize=8.5)
    axA.set_ylim(-0.6, len(rows) - 0.3); axA.set_yticks([])
    axA.set_xlim(-lim, lim)
    axA.set_xlabel("detuning from the calibrated resonance (Ω)")
    axA.set_title("A. The 15-point grid for three initial offsets: black ticks = hypotheses, ▼ = initial drive (grid centre), green = resonance;\n"
                  "orange / blue lines = alias teeth of the long (60.0 µs) / short (44.6 µs) gap", fontsize=9, loc="left")

    axB = fig.add_subplot(gs[1, 0])
    R = json.load(open(os.path.join(HERE, "order_sweep_85352.json")))
    pts = sorted([r for r in R if 2.0 <= r["q"] <= 3.0], key=lambda r: r["q"])
    fq = np.array([r["q"] - 2.0 for r in pts])
    axB.errorbar(fq, [r["hit21"] for r in pts], yerr=[r["hit21_sem"] for r in pts], fmt="o-", color="#eb6834", capsize=3, label="MAP on resonant point")
    axB.errorbar(fq, [r["pm1"] for r in pts], yerr=[r["pm1_sem"] for r in pts], fmt="s-", color="#8a8a8a", capsize=3, label="MAP on ±1 neighbour")
    axB.errorbar(fq, [r["pm2"] for r in pts], yerr=[r["pm2_sem"] for r in pts], fmt="^-", color="#4a3aa7", capsize=3, label="MAP on ±2 neighbour")
    axB.axvline(0.4, color="black", lw=1.0, alpha=0.5)
    axB.text(0.42, 0.015, "chosen 0.4", fontsize=8)
    axB.set_xlabel("frac(q), q = grid step (Hz) × T"); axB.set_ylabel("fraction of synthetic shots")
    axB.set_title("B. Hit vs where the grid samples the comb (model)", fontsize=9, loc="left")
    axB.legend(fontsize=7, loc="upper right"); axB.set_ylim(0, 0.5)

    axC = fig.add_subplot(gs[1, 1])
    fr = np.linspace(0, 1, 401)
    worst = np.array([min(abs(k * f - round(k * f)) for k in range(1, 5)) for f in fr])
    axC.plot(fr, worst, color="#4a3aa7", lw=1.6)
    axC.axvline(0.4, color="black", lw=1.0, alpha=0.5)
    for qv, lab, col in ((2.4, "long gap q 2.40", "#eb6834"), (2.4 * 44.6 / 60.0, "short gap q 1.78", "#2a78d6")):
        f = qv % 1
        w = min(abs(k * qv - round(k * qv)) for k in range(1, 5))
        axC.plot(f, w, "o", color=col, ms=7); axC.text(f + 0.02, w + 0.012, lab, fontsize=8, color=col)
    axC.set_xlabel("frac(q)"); axC.set_ylabel("closest of neighbours 1–4\nto a tooth (alias orders)")
    axC.set_title("C. Distance of the nearest grid neighbours from a tooth", fontsize=9, loc="left")
    axC.set_ylim(0, 0.27)
    fig.savefig(os.path.join(HERE, "fig_grid_construction.png"), dpi=160, bbox_inches="tight")
    for k, _ in rows:
        g, c = grid(k)
        print(k, "centre", round(c, 3), "range", round(g.min(), 3), round(g.max(), 3), "resonance index", int(np.argmin(np.abs(g))))


if __name__ == "__main__":
    main()
