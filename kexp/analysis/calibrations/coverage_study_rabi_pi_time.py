"""Coverage of rabi_pi_time's uncertainty on synthetic flops with a known pi time.

Run: ``python -m kexp.analysis.calibrations.coverage_study_rabi_pi_time`` (about
2-4 minutes). Deterministic: seed s of case c is numpy default_rng(1000*c + s).

For each case and each ``noise`` mode of waxa's fit_rabi it fits N_SEEDS
synthetic pulse-length scans through ``rabi_pi_time.calibrate`` and reports the
pull = (fitted t_pi - true t_pi) / reported unc. An honest uncertainty has pull
std ~1, ~68 % of pulls within 1 and ~95 % within 2. ``robust std`` (1.4826 MAD)
is shown beside the plain std so that one catastrophic fit is visible as such.

Synthetic flop: 41 pulse lengths over 0-20 us, f_Rabi = 75 kHz (t_pi = 6.6667
us), y = 652 + 400 (1 + exp(-t / 60 us) cos(2 pi f t)), with Gaussian noise of
sigma^2 = floor^2 + (frac (y - 652))^2 per shot: frac = 0 is plain additive
noise of sigma = floor; frac > 0 adds noise proportional to the signal above a
stable floor, like run 83092 (floor 24, frac 0.43 there).
Not a model of every real data set; a check that the error bars the analysis
writes are calibrated where the truth is known.

Imports nothing from the lab beyond waxx / waxa / this package; writes nothing.
"""

import numpy as np

F_RABI = 75.0e3
T_PI = 1 / (2 * F_RABI)
N_SEEDS = 300
MODES = ("auto", "pooled", "unweighted")
# (label, repeats, noise floor sigma, multiplicative fraction)
CASES = (
    ("additive 30, 3 repeats", 3, 30.0, 0.0),
    ("additive 30, 1 repeat", 1, 30.0, 0.0),
    ("additive 30, 10 repeats", 10, 30.0, 0.0),
    ("mult 0.10, 3 repeats", 3, 24.0, 0.10),
    ("mult 0.10, 5 repeats", 5, 24.0, 0.10),
    ("mult 0.25, 3 repeats", 3, 24.0, 0.25),
    ("mult 0.25, 5 repeats", 5, 24.0, 0.25),
)


def synthetic(rng, repeats, floor, frac):
    t = np.repeat(np.linspace(0.0, 20e-6, 41), repeats)
    y_true = 652 + 400 * (1 + np.exp(-t / 60e-6) * np.cos(2 * np.pi * F_RABI * t))
    sigma = np.sqrt(floor ** 2 + (frac * (y_true - 652)) ** 2)
    return t, y_true + rng.normal(0, 1, t.size) * sigma


def run(n_seeds=N_SEEDS):
    from types import SimpleNamespace
    from kexp.analysis.calibrations.rabi_pi_time import calibrate

    rows = []
    for c, (label, repeats, floor, frac) in enumerate(CASES):
        for mode in MODES:
            pulls, rel, fails = [], [], 0
            for s in range(n_seeds):
                t, y = synthetic(np.random.default_rng(1000 * c + s), repeats, floor, frac)
                ad = SimpleNamespace(xvarnames=["t_raman_pulse"], xvars=[t], atom_number=y,
                                     run_info=SimpleNamespace(run_id=0), params=None)
                r = calibrate(ad, "t_raman_pi_pulse", noise=mode)
                if not r.fit.get("ok") or r.unc is None:
                    fails += 1
                    continue
                pulls.append((r.value - T_PI) / r.unc)
                rel.append(r.value / T_PI - 1)
            p = np.asarray(pulls)
            if p.size:
                mad = 1.4826 * np.median(np.abs(p - np.median(p)))
                rows.append((label, mode, p.size, fails, p.std(), mad, np.mean(np.abs(p) < 1),
                             np.mean(np.abs(p) < 2), 100 * np.mean(rel), 100 * np.std(rel)))
            else:
                rows.append((label, mode, 0, fails) + (np.nan,) * 6)
    return rows


def summary(rows):
    head = (f"{'case':24} {'noise':10} {'n':>4} {'fail':>4} {'pull std':>8} {'robust':>7} "
            f"{'|p|<1':>6} {'|p|<2':>6} {'bias %':>7} {'rms %':>6}")
    lines = [head, "-" * len(head)]
    for (label, mode, n, fails, sd, rsd, w1, w2, bias, rms) in rows:
        lines.append(f"{label:24} {mode:10} {n:4d} {fails:4d} {sd:8.2f} {rsd:7.2f} "
                     f"{w1:6.2f} {w2:6.2f} {bias:+7.3f} {rms:6.3f}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary(run()))
