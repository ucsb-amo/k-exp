"""Parameters of the adaptive Ramsey test experiment (2026-10-30, DESIGN STAGE).

The feedback calibration (APD endpoints, photon numbers, light shift, read model, t_pi) is the
shipped one from expt_params_feedback; only the protocol differs. The hypothesis grid is finer
than production's (step ~300 Hz) because the protocol is meant to end below 1 kHz; the slack --
and with it the gap floor, which sets the first fringe -- is a GUESS (kexp.analysis.adaptive_ramsey
.slack_estimate_s) until the first run's data.ramsey_timing says what the kernel really needs.
"""
import numpy as np
from numpy import int64

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback
from kexp.base.adaptive_ramsey import adaptive_ramsey_param_defaults, PHASE_MAXVAR, GAP_MAXVAR


class ExptParams(ExptParamsFeedback):
    def __init__(self):
        super().__init__()
        adaptive_ramsey_param_defaults(self)

        ### protocol (kexp.base.adaptive_ramsey)
        self.ramsey_phase_policy = PHASE_MAXVAR
        self.ramsey_gap_policy = GAP_MAXVAR
        self.ramsey_gap_candidates = np.array([1., 2., 4., 8.])   # x the gap floor
        self.ramsey_gap_maxvar_margin = 0.05
        self.t_ramsey_gap_max = 300.e-6      # user 2026-10-30: cap gaps at 300 us, coherence time is a limitation
        self.t_ramsey_total_max = 4.0e-3
        self.ramsey_pulse_area_pi = 0.5
        self.ramsey_phase_sign = 1.0           # UNVERIFIED on hardware; see the phase-sign check
        self.ramsey_phase_seed = 0
        self.t_ramsey_phase_set_pretrigger_mu = int64(12000)

        ### the estimator: drive fixed (no hop), fixed pi/2 pulses, no pre-shot
        self.update_raman_frequency_bool = 0
        self.t_raman_pulse_random_bool = 0
        self.preshot_contrast = 0
        self.N_pulses = 12
        self.N_repeats = 5
        self.feedback_grid_convention = 2
        self.feedback_grid_size = 41
        self.frequency_feedback_grid_full_span = 12.e3
        self.feedback_fractional_initial_offset = 0.0
        self.feedback_grid_shift = 0.0
        self.feedback_remesh_threshold_Omega = 0.0

        # every pulse pi/2 at the rate pi time plus the turn-on offset (the list the base draws
        # with t_raman_pulse_random_bool = 0 is this constant)
        self.t_raman_pulse = self.ramsey_pulse_area_pi * self.t_raman_pi_pulse + self.t_raman_pulse_offset
        self.t_raman_pulse_ideal = self.t_raman_pulse - self.t_raman_pulse_offset

        ### timing: slack = posterior + plan + set(relative_phase) -- the simulator's guess
        from kexp.analysis.adaptive_ramsey import slack_estimate_s
        self.t_calculation_slack_compensation_mu = int64(
            slack_estimate_s(self.feedback_grid_size, len(self.ramsey_gap_candidates)) * 1.e9) & ~7

        self.compute_feedback_grid()
