from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
import numpy as np

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
# from base_expt_feedback_fast import FeedbackExptFast as FeedbackExpt  # session copy: fast path (overlapped ADC read, pre-issued next read)
from base_expt_feedback_grid import FeedbackExptGrid as FeedbackExpt  # session copy 2026-10-08 00:1x: alt gaps + grid from the pulse period (DESIGN_grid_rule.md); non-adaptive  # session copy 2026-10-07 ~23:1x (user: non-adaptive version of ALT2): fast path + alternating extra gap, as feedback_alt2.py


def hypothesis_grid_omega(offset, span, f_res, t_pi, m, center_exact=1):
    """Host numpy mirror of Feedback._initialize_frequency_grid (kexp/base/feedback.py),
    term for term: centre = offset (center_exact 1) or round(offset) (0);
    w_j = omega_res + Omega * (centre - span * (-1 + 2 j / (m - 1))), then shifted so
    the first grid point nearest resonance sits exactly on it. Returns (grid, zidx).
    Kept here because feedback_grid_omega exists only on the OPX branch."""
    Omega = np.pi / t_pi
    omega_res = 2.0 * np.pi * f_res
    centre = offset if center_exact else float(round(offset))
    t = -1.0 + np.arange(m, dtype=np.float64) * (2.0 / (m - 1))
    grid = omega_res + Omega * (centre - span * t)
    zidx = int(np.argmin(np.abs(grid - omega_res)))
    return grid + (omega_res - grid[zidx]), zidx


class feedback_random_bayesian(EnvExperiment, FeedbackExpt):
    """Non-adaptive Bayesian: pulse 0 drives the initial offset, exactly where the
    adaptive loop starts (reset_initial_omega_from_params: omega_res + Omega *
    feedback_fractional_initial_offset). Pulses 1..N_pulses-1 drive hypothesis-grid
    points whose INDICES are drawn per shot without replacement, in random order,
    from every grid index except the one nearest pulse 0 (the grid centre when the
    offset is a whole number of grid steps from resonance, so pulse 0 is that grid
    point). Runs the same posterior update as the adaptive feedback
    (update_raman_frequency_bool = 0, so the drive never follows the posterior).

    The counterpart of feedback_fast for adaptive-vs-non-adaptive comparisons:
    same grid (feedback_grid_size, feedback_guess_span_Omega, the initial offset
    placing it), same first pulse, same number of pulses, same pulse durations
    (the t_raman_pulse_seed draw), same readout. Only the choice of drive
    frequency after pulse 0 differs. The drive of every pulse is saved per shot
    in data.omega_raman.

    A fresh draw every shot (p.pulse_list_seed = 0); a non-zero seed repeats one
    list for every shot.
    """

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)

        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.feedback_fractional_initial_offset = 2.
        # self.xvar('feedback_fractional_initial_offset', np.linspace(-2.5, 2.5, 11))
        ### grid from the pulse period (user 2026-10-07 23:2x: 15 points, q = n + 0.4, 9 pulses per preparation)
        self.p.N_pulses = 9
        self.p.feedback_grid_size = 15
        self.p.feedback_grid_alias_frac = 0.4
        self.p.feedback_grid_alias_order = -1
        self.p.feedback_grid_alias_T_ref = "long"
        self.p.t_calculation_slack_compensation_mu = np.int64(18000) # fast path, 15-pt bench 2026-10-07 23:44 (85431-85434): floor 14 us + 4
        self.p.t_gap_cycle_extra_us = np.array([0., 15.])     # ALT2 gaps; 15 us from the X sweep for the rule grid (REPORT Addendum 5)
        self.p.feedback_remesh_threshold_Omega = 0.0
        step = self.grid_step_Omega()
        # initial offsets on grid points, step * k, k = -7..7 (15 values, within the span)
        self.xvar('feedback_fractional_initial_offset', step * np.arange(-7., 8.))

        self.p.pulse_list_seed = 0

        # self.p.N_warmup_shots = 3 # session copy: 3 warm-up shots (Base.pre_scan)
        self.p.N_warmup_shots = 20 # session copy 2026-10-07 ~19:40 (user: more warm-up shots, like 20)
        # self.p.N_repeats = 20 # session copy 2026-10-07 ~19:40 (user: "Do 20 repeats"; was the params default 5)
        self.p.N_repeats = 13 # session copy 2026-10-07 ~23:1x (user: ~0.66 x the 20 repeats, alternate ALT2 / NAALT2 more often)
        self.finish_prepare()

    @rpc
    def get_new_pulse_list(self, seed=0) -> TArray(TFloat):
        '''Pulse 0 at the initial offset, then N_pulses - 1 distinct grid
        frequencies in random order (see the class docstring).

        Called every shot from scan_kernel, after the scanner has written this
        shot's xvar values into the host params, so the offset read here is the
        current one. The grid is rebuilt from those params exactly as
        Feedback._initialize_frequency_grid builds it (hypothesis_grid_omega above
        is its numpy mirror, snap to resonance and grid-centre rule included):
        scan_kernel calls this BEFORE initialize_feedback(), so
        p.omega_guess_list may still hold the previous shot's grid when the
        initial offset is scanned.
        '''
        m = int(self.p.feedback_grid_size)
        n = int(self.p.N_pulses)
        if n > m:
            raise ValueError(f"N_pulses = {n} exceeds feedback_grid_size = {m}: "
                             "cannot draw that many distinct grid points.")
        offset = float(np.ravel(self.p.feedback_fractional_initial_offset)[0])
        span = float(np.ravel(self.p.feedback_guess_span_Omega)[0])
        f_res = float(np.ravel(self.p.frequency_raman_transition)[0])
        t_pi = float(np.ravel(self.p.t_raman_pi_pulse)[0])
        center_exact = int(getattr(self.p, "feedback_grid_center_exact_offset", 0))
        omega_grid, _ = hypothesis_grid_omega(offset, span, f_res, t_pi, m, center_exact)
        # the adaptive loop's first drive (Feedback.reset_initial_omega_from_params)
        omega_first = 2.0 * np.pi * f_res + (np.pi / t_pi) * offset
        idx_first = int(np.argmin(np.abs(omega_grid - omega_first)))
        rng = np.random.default_rng(int(seed) if seed != 0 else None)
        idx = rng.choice(np.delete(np.arange(m), idx_first), size=n - 1, replace=False)
        self.p.omega_pulse_list = np.concatenate(([omega_first], omega_grid[idx]))
        return self.p.omega_pulse_list

    @kernel
    def per_feedback_loop_top(self, idx):
        self.omega_raman = self.p.omega_pulse_list[idx]

    @kernel
    def per_feedback_loop_end(self, idx):
        # +1: row 0 holds the prior, before the first pulse
        self.data.probabilities.put_data_1d(self.P0, i=idx+1)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, notify=False, restart_monitor=False)
