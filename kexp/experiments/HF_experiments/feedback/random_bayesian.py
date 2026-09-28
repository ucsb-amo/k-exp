from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
import numpy as np

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt


class feedback_random_bayesian(EnvExperiment, FeedbackExpt):
    """Non-adaptive Bayesian: each shot drives N_pulses DISTINCT hypothesis-grid
    points in a random order, drawn without replacement, and runs the same
    posterior update as the adaptive feedback (update_raman_frequency_bool = 0,
    so the drive never follows the posterior).

    The counterpart of feedback_fast for adaptive-vs-non-adaptive comparisons:
    same grid (feedback_grid_size, feedback_guess_span_Omega, the initial offset
    placing it), same number of pulses, same pulse durations (the
    t_raman_pulse_seed draw), same readout. Only the choice of drive frequency
    differs. The drive of every pulse is saved per shot in data.omega_raman.

    A fresh draw every shot (p.pulse_list_seed = 0); a non-zero seed repeats one
    list for every shot.
    """

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)

        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.N_repeats = 21
        self.p.N_pulses = 17 # number of steps of evolution (<= feedback_grid_size)

        # 21 hypotheses at 0.25 Omega: feedback_guess_span_Omega is the grid
        # HALF-width, so the step is 2 * 2.5 / 20.
        self.p.feedback_grid_size = 21
        self.p.feedback_guess_span_Omega = 2.5

        self.p.feedback_fractional_initial_offset = 2.
        # self.xvar('feedback_fractional_initial_offset', np.linspace(-2.5, 2.5, 11))

        self.p.pulse_list_seed = 0

        self.finish_prepare()

    @rpc
    def get_new_pulse_list(self, seed=0) -> TArray(TFloat):
        '''N_pulses distinct grid frequencies in random order.

        The grid is rebuilt here from the current params, exactly as
        Feedback._initialize_frequency_grid builds it (feedback_grid_omega is
        its numpy mirror, snap to resonance and grid-centre rule included):
        scan_kernel calls this BEFORE initialize_feedback(), so
        p.omega_guess_list may still hold the previous shot's grid when the
        initial offset is scanned.
        '''
        from kexp.base.feedback import feedback_grid_omega
        m = int(self.p.feedback_grid_size)
        n = int(self.p.N_pulses)
        if n > m:
            raise ValueError(f"N_pulses = {n} exceeds feedback_grid_size = {m}: "
                             "cannot draw that many distinct grid points.")
        offset = float(np.ravel(self.p.feedback_fractional_initial_offset)[0])
        span = float(np.ravel(self.p.feedback_guess_span_Omega)[0])
        f_res = float(np.ravel(self.p.frequency_raman_transition)[0])
        omega_grid, _ = feedback_grid_omega(self.p, fractional_initial_offset=offset,
                                            guess_span_Omega=span,
                                            frequency_raman_transition=f_res,
                                            feedback_grid_size=m)
        rng = np.random.default_rng(int(seed) if seed != 0 else None)
        idx = rng.choice(m, size=n, replace=False)
        self.p.omega_pulse_list = omega_grid[idx]
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
        self.end(expt_filepath)
