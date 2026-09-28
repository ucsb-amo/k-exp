"""QOP-simulator timing of the OPX feedback loop, split update off vs on (2026-09-28).

*** NOT YET RUN. *** OPXBench.simulate connects to the QM server (the OPX
must be reachable); nothing is played on hardware, but check that no one
is using the OPX before running it. Run from the workspace root:

    .venv/Scripts/python k-exp/docs/opx/sim_split_timing.py

Method (as the 2026-09-25 pass-3b measurement in the sequence docstring):
m = 21, N_pulses = 6, one shot, the pulse-start timestamps
(t_pulse_start_cc) of the simulated program.

1. Compute-bound: t_opx_feedback_compute_budget collapsed to 16 ns, so the
   next pulse waits for the update; the excess of each pulse-start interval
   over d_i + 2 edge + t_img is readback + post-read update + sync. For the
   default structure this was 1938 cc (continuous, sincos table) and 1074 cc
   (16 levels). The split would cut it to roughly the likelihood + argmax
   only if the thread ran the measurement-independent half while the ADC
   result is pending -- EXPECT NO GAIN (review 2026-09-28): ctx.measure
   saves the ADC value right after the measure statement, so the thread
   already waits there in both structures, and on QOP 2.6 reordering the
   prediction around the pulse statements measurably did not help
   (feedback_port_report.md). If step 1 shows no reduction, remove the
   option.
2. Real budget (10 us): the excess of each interval over the full schedule
   term d_i + 2 edge + t_img + budget is the structure's sync overhead --
   the value t_opx_feedback_align_overhead[_levels]_split must be set to
   (the run is traced with the non-split value as a placeholder, so the
   slip column shows how far that placeholder is off).

What to do with the numbers: set the two *_split overheads in
expt_params_feedback_opx.py from step 2, pick a budget that covers step 1
with margin (the default kept 28-35 %), then opx_feedback_split_update = 1;
the finish hook's slip line keeps checking on hardware.
"""

import numpy as np

from kexp.control.opx import OPXBench
from kexp.control.opx.units import CLOCK_NS
from kexp.experiments.HF_experiments.feedback.expt_params_feedback_opx import ExptParams
from kexp.experiments.opx_sequences.feedback import (
    bayesian_feedback, feedback_constants, build_feedback_shot_tables, BLOCK_EDGE_CC)

N_PULSES, M, SEED = 6, 21, 11
PLACEHOLDER = {0: 328.e-9, 8: 344.e-9}     # the non-split overheads (s), continuous / levels


def fetch(job, key):
    rh = job.result_handles
    rh.wait_for_all_values()
    v = np.asarray(rh.get(key).fetch_all())
    if v.dtype.names:
        v = v['value']
    return v.reshape(-1)


def run(split, levels, budget_s):
    p = ExptParams()
    p.N_pulses, p.feedback_grid_size = N_PULSES, M
    p.t_raman_pulse_n_levels = levels
    p.t_opx_feedback_compute_budget = budget_s
    p.opx_feedback_split_update = split
    p.t_raman_pulse_seed = float(SEED)
    if split:
        key = ('t_opx_feedback_align_overhead_levels_split' if levels
               else 't_opx_feedback_align_overhead_split')
        setattr(p, key, PLACEHOLDER[levels])
    c = feedback_constants(lambda k: getattr(p, k))
    T = build_feedback_shot_tables(lambda k: np.asarray([getattr(p, k)], dtype=float), 1, c)
    bench = OPXBench(expt_params=p)
    bench.xvar('t_raman_pulse_seed', np.array([float(SEED)]))
    # timeline long enough for N pulses at the real budget
    dur = 1.e-9 * CLOCK_NS * float(T.t_start_ext_cc[0, -1]) + 100.e-6
    job = bench.simulate(bayesian_feedback, duration=dur, shots=1, viewer=False, web_plot=False)
    t = fetch(job, 't_pulse_start_cc').astype(np.int64)
    iv = np.diff(t)
    d = T.d_cc[0, :iv.size]
    base = d + 2 * BLOCK_EDGE_CC + c.t_img_cc
    return dict(intervals=iv, excess_over_pulse_img=iv - base,
                excess_over_budget=iv - base - c.budget_cc,
                slip=iv - T.gap_cc[0, :iv.size], overhead_cc=c.overhead_cc)


if __name__ == '__main__':
    for levels in (0, 8):
        for split in (0, 1):
            tag = f"levels {levels:2d}, split {split}"
            r = run(split, levels, 16.e-9)
            print(f"{tag} | compute-bound: excess over d + 2 edge + t_img = "
                  f"{r['excess_over_pulse_img'].tolist()} cc")
            r = run(split, levels, 10.e-6)
            print(f"{tag} | 10 us budget: excess over the schedule without the overhead = "
                  f"{r['excess_over_budget'].tolist()} cc (overhead now {r['overhead_cc']} cc); "
                  f"slip vs schedule = {r['slip'].tolist()} cc")
