"""QOP-simulator timing of the OPX remesh sequence (bayesian_feedback_remesh, 2026-09-28).

*** NOT YET RUN. *** OPXBench.simulate connects to the QM server (the OPX
must be reachable); nothing is played on hardware, but check that no one
is using the OPX before running it. Run from the workspace root:

    .venv/Scripts/python k-exp/docs/opx/sim_remesh_timing.py

The remesh structure needs three measured values before it traces
(feedback_constants refuses without them):

    t_opx_feedback_align_overhead[_levels][_split]_remesh   sync overhead
    t_opx_feedback_compute_budget[_levels][_split]_remesh   compute budget
    t_opx_remesh_hold                                        pole step's extra hold

Method (as sim_split_timing.py): m = 21, N_pulses = 10, one shot, the pulse
start timestamps (t_pulse_start_cc) and the recorded pole pulse / level.
The pole pulse is FORCED inside the trigger window (min_pulse 2, force 3:
the trigger fires after pulse 2 at the latest, the pole pulse is 3), so
every run has one pole step to time.

1. Compute-bound: budget 16 ns, hold 0. The excess of each interval over
   d_i + 2 edge + t_img is readback + the update + the per-pulse trigger
   block + sync; at the pole step also the remesh block. The ordinary
   steps give the remesh budget (with margin, the default kept 28-35 %),
   the pole step's extra over them gives t_opx_remesh_hold.
2. Placeholders in: every interval should equal the schedule
   (remesh_pulse_starts_cc: ARTIQ's step formula with the APPLIED
   durations, the pole step + the hold); the constant excess is the
   structure's sync overhead. Report it per interval, pole step marked.

What to do with the numbers: set the three keys in expt_params_feedback_opx.py
(tagged with the date and "simulator"), then run again: step 2 must show a
zero slip on EVERY interval, the pole step included. The finish hook's slip
line keeps checking on hardware.
"""

import numpy as np

from kexp.control.opx import OPXBench
from kexp.control.opx.units import CLOCK_NS
from kexp.experiments.HF_experiments.feedback.expt_params_feedback_opx import ExptParams
from kexp.experiments.opx_sequences.feedback import (
    bayesian_feedback_remesh, feedback_constants, build_feedback_shot_tables,
    pole_level_durations_cc, remesh_pulse_starts_cc, BLOCK_EDGE_CC)

N_PULSES, M, SEED = 10, 21, 11
# placeholders so the structure traces: the plain structures' measured values
PLACEHOLDER_OVERHEAD = {0: 328.e-9, 8: 344.e-9}
PLACEHOLDER_BUDGET = 10.e-6
PLACEHOLDER_HOLD = 4.e-6


def fetch(job, key):
    rh = job.result_handles
    rh.wait_for_all_values()
    v = np.asarray(rh.get(key).fetch_all())
    if v.dtype.names:
        v = v['value']
    return v.reshape(-1)


def run(levels, budget_s, hold_s, split=0):
    p = ExptParams()
    p.N_pulses, p.feedback_grid_size = N_PULSES, M
    p.t_raman_pulse_n_levels = levels
    p.opx_feedback_split_update = split
    p.opx_remesh_enable = 1
    p.feedback_reinit_min_pulse = 2
    p.feedback_reinit_force_pulse = 3
    p.t_raman_pulse_seed = float(SEED)
    suffix = ('_levels' if levels else '') + ('_split' if split else '') + '_remesh'
    setattr(p, 't_opx_feedback_align_overhead' + suffix, PLACEHOLDER_OVERHEAD[levels])
    setattr(p, 't_opx_feedback_compute_budget' + suffix, budget_s)
    p.t_opx_remesh_hold = hold_s
    c = feedback_constants(lambda k: getattr(p, k))
    T = build_feedback_shot_tables(lambda k: np.asarray([getattr(p, k)], dtype=float), 1, c)
    bench = OPXBench(expt_params=p)
    bench.xvar('t_raman_pulse_seed', np.array([float(SEED)]))
    pole_d_cc, _a, _b = pole_level_durations_cc(c)
    # long enough for N pulses plus the longest pole step and the hold
    dur = (1.e-9 * CLOCK_NS * (float(T.t_start_ext_cc[0, -1]) + int(pole_d_cc.max())
                               + c.remesh_hold_cc) + 100.e-6)
    job = bench.simulate(bayesian_feedback_remesh, duration=dur, shots=1, viewer=False,
                         web_plot=False)
    t = fetch(job, 't_pulse_start_cc').astype(np.int64)
    rp = int(fetch(job, 'remesh_pulse')[0])
    k = int(fetch(job, 'remesh_pole_level')[0])
    d_app = T.d_cc[0].copy()
    if rp >= 0:
        d_app[rp] = pole_d_cc[k]
    iv = np.diff(t)
    base = d_app[:iv.size] + 2 * BLOCK_EDGE_CC + c.t_img_cc
    sched = remesh_pulse_starts_cc(d_app[None], c, [rp])[0]
    return dict(pole_pulse=rp, pole_level=k, intervals=iv,
                excess_over_pulse_img=iv - base,
                slip=iv - np.diff(sched)[:iv.size], overhead_cc=c.overhead_cc,
                budget_cc=c.budget_cc, hold_cc=c.remesh_hold_cc)


def show(tag, r, key):
    marks = ['*' if i == r['pole_pulse'] else ' ' for i in range(r[key].size)]
    cells = ' '.join(f"{v:6d}{m}" for v, m in zip(r[key].tolist(), marks))
    print(f"{tag} | {key} (interval i -> i+1, * = the pole step, pole level "
          f"{r['pole_level']}): {cells}")


if __name__ == '__main__':
    for levels in (0, 8):
        tag = f"levels {levels:2d}"
        r = run(levels, 16.e-9, 0.0)
        if r['pole_pulse'] != 3:
            print(f"{tag} | WARNING: the pole pulse is {r['pole_pulse']}, not the forced 3")
        show(tag + ' compute-bound', r, 'excess_over_pulse_img')
        r = run(levels, PLACEHOLDER_BUDGET, PLACEHOLDER_HOLD)
        show(tag + f" placeholders (overhead {r['overhead_cc']} cc, budget "
             f"{r['budget_cc']} cc, hold {r['hold_cc']} cc)", r, 'slip')
