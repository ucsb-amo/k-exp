"""Discrete pulse-duration levels vs the continuous draw: closed-loop
wrong-grid-point rate of the OPX feedback posterior.

The numbers quoted in kexp.base.feedback.t_raman_pulse_level_set come from
this script. Per seed: the true detuning sits on a grid point drawn
uniformly over the m points, a synthetic APD with photon noise steps the
true Bloch vector by the reset phase model (the tests' detector), and the
float64 emulation of the OPX loop (run_shot_fixed_point_emulation) runs
the shot closed-loop from the params' tables. Metric: the final argmax is
not the true grid point.

    python docs/opx/alias_levels_study.py <n_seeds> <config> [<config> ...]
    config = span,offset,n1/n2/...[,N_pulses]     (n = 0: continuous draw)

e.g. 3000 "5,0,0/2/3/4/5/6/8/11" "3,2,0/2/3/4/8" "5.4,0,0/2/3/4/8"
"5,0,0/2/4/8,60" reproduces the 2026-09-26 table (about 5 ms per shot).
Offline only; other params are the tests' _params() (ExptParamsFeedbackOPX,
m = 21). MIN_PULSE_LEVELS is lowered in-process so 2 and 3 levels can run.
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', 'tests'))

import test_feedback_opx as TF                                       # noqa: E402
from kexp.analysis.feedback_opx import (run_shot_fixed_point_emulation,  # noqa: E402
                                        true_bloch_step)
from kexp.experiments.opx_sequences import feedback as fbseq          # noqa: E402

fbseq.MIN_PULSE_LEVELS = 1


def bounds(p):
    """(phase bound, fold bound) on n_levels - 1, t_raman_pulse_level_set."""
    frac = p.t_raman_pulse_max_frac_pi - p.t_raman_pulse_min_frac_pi
    span = p.feedback_guess_span_Omega
    return frac * span, frac * np.sqrt(1. + (2. * span) ** 2)


def run(span, offset, n_levels, n_seeds, N=20, seed0=1000):
    p = TF._params(N=N, m=21, span=span, offset=offset,
                   t_raman_pulse_n_levels=n_levels)
    c = TF._const(p)
    seeds = np.arange(seed0, seed0 + n_seeds)
    T = TF._tables_for(p, seeds)
    fb = TF._artiq_feedback(p)            # once: its LUT is expensive
    wrong = 0
    for s in range(n_seeds):
        rng_t = np.random.default_rng([int(seeds[s]), 1])
        rng_n = np.random.default_rng([int(seeds[s]), 2])
        j_true = int(rng_t.integers(c.m))
        omega_true = c.omega_res + c.Omega * float(T.w_grid[s, j_true])
        st = {'s': (0.0, 0.0, 1.0)}
        d_s, t_in = T.d_s[s], T.t_start_s[s]

        def measure(i, w_d):
            omega_ctrl = c.omega_res + c.Omega * float(w_d)
            hz, st['s'] = true_bloch_step(
                st['s'], omega_ctrl, omega_true, d_s[i] - c.t_offset_s,
                d_s[i], t_in[i], c.Omega, 2 * np.pi * p.frequency_lightshift,
                c.t_img_s, c.C)
            return (float(fb.expected_photon_fraction(hz))
                    + rng_n.normal(0.0, c.sigma_p))

        out = run_shot_fixed_point_emulation(
            T.w_grid[s], int(T.zidx[s]), T.a[s], T.b[s], T.dphi0[s],
            T.ddphi[s], c, measure, d_init=int(T.d_init[s]))
        wrong += int(np.argmax(out['P0'][-1]) != j_true)
    r = wrong / n_seeds
    return r, np.sqrt(r * (1 - r) / n_seeds), p


def main():
    n_seeds = int(sys.argv[1])
    for cfg in sys.argv[2:]:
        parts = cfg.split(',')
        span, offset = float(parts[0]), float(parts[1])
        ns = [int(n) for n in parts[2].split('/')]
        N = int(parts[3]) if len(parts) > 3 else 20
        header = False
        for n in ns:
            t0 = time.time()
            r, e, p = run(span, offset, n, n_seeds, N=N)
            if not header:
                b_phase, b_fold = bounds(p)
                print(f'--- span {span:g}, offset {offset:g}, N_pulses {N}: '
                      f'n - 1 > {b_phase:.2f} (phase), > {b_fold:.2f} (fold)',
                      flush=True)
                header = True
            tag = 'continuous' if n == 0 else f'{n:2d} levels'
            below = n and (n - 1 <= bounds(p)[1])
            print(f'  {tag:11s} wrong {r:6.3f} +- {e:.3f}   '
                  f'[{time.time() - t0:5.1f} s]'
                  + ('  (below the fold bound)' if below else ''), flush=True)


if __name__ == '__main__':
    main()
