from artiq.experiment import *
from artiq.language import TFloat, TArray
from kexp.base.feedback import feedback_grid_convention, feedback_hypothesis_grid, feedback_offset_frac
import numpy as np

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt


def maximin_grid_order(m, n_pulses):
    """Order in which to visit grid indices: centre first, then farthest-from-visited (greedy maximin).

    Ties go to the candidate farthest from the last index, then opposite the centre from it, then
    the lower index. Worse than the sweep in get_new_pulse_list (see the comment there).

    Returns an int array of length min(n_pulses, m); indices never repeat.
    """
    centre = (m - 1) / 2.0
    order = [int(round(centre))]
    remaining = [i for i in range(m) if i != order[0]]
    while len(order) < int(n_pulses) and remaining:
        chosen = np.asarray(order)
        best, best_key = None, None
        for i in remaining:
            min_dist = int(np.min(np.abs(chosen - i)))
            dist_last = abs(i - order[-1])
            opposite = 1 if (i - centre) * (order[-1] - centre) <= 0 else 0
            key = (min_dist, dist_last, opposite, -i)
            if best_key is None or key > best_key:
                best_key, best = key, i
        order.append(best)
        remaining.remove(best)
    return np.array(order, dtype=int)


class feedback_deterministic_bayesian(EnvExperiment, FeedbackExpt):

    def prepare(self):

        FeedbackExpt.__init__(self,
                      save_data=True,
                      save_on_underflow=True)
        
        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.N_repeats = 21
        self.p.N_pulses = 9 # number of steps of evolution
        
        ### parameters

        # Hypothesis grid (feedback_grid_convention 2, kexp.base.feedback): 21 points over
        # the default full width (frequency_feedback_grid_full_span)
        self.p.feedback_grid_size = 21
        # self.p.frequency_feedback_grid_full_span = 509.8e3 # 4 Omega at t_pi 3.9229 us, the old +-2 Omega
        # self.p.feedback_guess_span_Omega = 2.0 # convention 1

        # Slide the grid across resonance: the kernel snaps a point onto resonance, so an offset of k
        # steps moves WHICH INDEX is resonant, testing the truth near the edge of the prior. As a
        # fraction of the largest allowed, (m - 2) / 2 = 9.5 steps: resonance on indices 1, 5, 10, 15, 19.
        offset_steps = np.array([-9.5, -5., 0., 5., 9.5])
        self.xvar('feedback_fractional_initial_offset',
                  feedback_offset_frac(offset_steps, self.p.feedback_grid_size))

        self.finish_prepare()

    @rpc
    def get_new_pulse_list(self, seed=0) -> TArray(TFloat):
        '''N_pulses points swept monotonically across the grid; seed is unused.

        The grid is rebuilt here (feedback_hypothesis_grid, the host copy of
        Feedback._initialize_frequency_grid): scan_kernel calls this before initialize_feedback(),
        so p.omega_guess_list still holds the previous shot's grid, and this experiment scans it.
        '''
        m = int(self.p.feedback_grid_size)
        Omega = np.pi / float(self.p.t_raman_pi_pulse)
        omega_res = 2.0 * np.pi * float(np.ravel(self.p.frequency_raman_transition)[0])
        span = float(np.ravel(self.p.feedback_guess_span_Omega)[0])
        # the whole xvar array during prepare, this shot's scalar afterwards
        offset = float(np.ravel(self.p.feedback_initial_offset_Omega)[0])
        shift = float(np.ravel(self.p.feedback_grid_shift)[0])

        omega_grid, _, _ = feedback_hypothesis_grid(
            omega_res, Omega, span, m, offset, grid_shift=shift,
            convention=feedback_grid_convention(self.p),
            center_exact=int(self.p.feedback_grid_center_exact_offset))

        # Monotonic sweep. maximin_grid_order was worse on synthetic data at 17 pulses (hit rate 0.205 +/-
        # 0.012 against 0.256 +/- 0.008 over 4 noise seeds, -0.15 to -0.21 bias slope): re-measure first.
        sample_idx = np.rint(np.linspace(0, m - 1, self.p.N_pulses))
        sample_idx = np.clip(sample_idx, 0, m - 1).astype(int)
        self.p.omega_pulse_list = omega_grid[sample_idx]
        return self.p.omega_pulse_list

    @kernel
    def per_feedback_loop_top(self, idx):
        self.omega_raman = self.p.omega_pulse_list[idx]

    @kernel
    def per_feedback_loop_end(self, idx):
        # +1: row 0 holds the prior
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