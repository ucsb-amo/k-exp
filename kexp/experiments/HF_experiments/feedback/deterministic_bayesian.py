from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.util.artiq.async_print import aprint

from kexp.experiments.HF_experiments.feedback.base_expt_feedback import FeedbackExpt


def maximin_grid_order(m, n_pulses):
    """Order in which to visit grid indices: centre first, then farthest-from-visited.

    A greedy maximin ("farthest point") sequence. Pulse 1 sits at the grid
    centre; every later pulse goes to the unvisited index whose MINIMUM distance
    to all already-visited indices is largest.

    WHY NOT JUST SWEEP THE GRID IN ORDER.  The obvious schedule --
    rint(linspace(0, m-1, N_pulses)) -- walks the grid monotonically, which
    makes pulse index and drive frequency 99.9% correlated (0.093 for this
    ordering).  Measurement back-action damps the transverse Bloch component
    every cycle, so early pulses carry far more information than late ones; with
    a monotonic sweep that puts all the informative pulses at one end of the
    grid, and the posterior inherits a bias toward that end no matter where
    resonance actually is.  Spreading the early pulses across the whole grid
    removes the confound.

    Ties are broken deterministically, and symmetrically in the sense that the
    sequence alternates sides of the grid rather than favouring one:
      1. prefer the candidate farthest from the MOST RECENTLY visited index;
      2. then one on the opposite side of the centre from the last index;
      3. then the lower index, purely so the result is reproducible.
    For m = 21, N_pulses = 17 this gives detunings
    0, +3, -3, +1.5, -1.5, +2.4, -2.4, +0.9, -0.9, ... in units of the span.

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

        # Hypothesis grid. feedback_guess_span_Omega is a HALF-width: the grid
        # runs from offset-span to offset+span, so span = 3 gives a 6*Omega-wide
        # grid and, at 21 points, a step of 0.3*Omega.
        self.p.feedback_grid_size = 21
        self.p.feedback_guess_span_Omega = 2.0

        # Slide the grid across resonance, one grid step per point. The kernel
        # snaps the grid so its nearest point lands exactly on resonance
        # (_initialize_frequency_grid), so an offset of k grid steps does not
        # move the grid frequencies off resonance -- it moves WHICH INDEX is the
        # resonant one. Over -span..+span in 21 steps the resonance index walks
        # 0, 1, ... 20: from the grid edge, through the centre, to the far edge.
        # That is the thing being scanned -- how the posterior behaves when the
        # truth sits at the edge of the prior rather than its middle.
        # 5 offsets over the full grid width. At span 2 / 21 points the grid step
        # is 0.2 Omega, so these land the resonance on grid indices 0, 5, 10, 15,
        # 20 -- edge, quarter, centre, quarter, edge.
        self.xvar('feedback_fractional_initial_offset',
                  np.linspace(-self.p.feedback_guess_span_Omega,
                              self.p.feedback_guess_span_Omega, 5))

        self.finish_prepare()

    @rpc
    def get_new_pulse_list(self, seed=0) -> TArray(TFloat):
        '''linearly spaced (rounded to grid)

        seed is accepted to match the base-class signature but is unused: this
        experiment's pulse list is fully deterministic (grid-indexed), so
        p.pulse_list_seed has no effect here.

        The grid is REBUILT here from the current params rather than read off
        p.omega_guess_list. That is not redundancy -- scan_kernel calls this
        BEFORE initialize_feedback(), so p.omega_guess_list still holds the
        PREVIOUS shot's grid at this point. That does not matter while the grid
        is constant across shots, but this experiment scans
        feedback_fractional_initial_offset, which moves the grid every shot, and
        reading the stale list would drive shot N at shot N-1's frequencies --
        silently, and in exactly the quantity being scanned.

        The construction below mirrors Feedback._initialize_frequency_grid,
        snap included. Keep the two in sync if that function changes.
        '''
        m = int(self.p.feedback_grid_size)
        Omega = np.pi / float(self.p.t_raman_pi_pulse)
        omega_res = 2.0 * np.pi * float(np.ravel(self.p.frequency_raman_transition)[0])
        span = float(np.ravel(self.p.feedback_guess_span_Omega)[0])
        # During prepare this may still be the whole xvar array; per shot the
        # scan machinery has already plugged in that shot's scalar.
        offset = float(np.ravel(self.p.feedback_fractional_initial_offset)[0])

        t = np.linspace(-1.0, 1.0, m)
        omega_grid = omega_res + Omega * (offset - span * t)
        # Shift so the nearest grid point lands exactly on resonance.
        best_idx = int(np.argmin(np.abs(omega_grid - omega_res)))
        omega_grid = omega_grid + (omega_res - omega_grid[best_idx])

        # Monotonic sweep of the grid. maximin_grid_order (below) was tried as an
        # alternative -- centre-out, to decorrelate pulse index from drive
        # frequency, since back-action makes early pulses dominate. On synthetic
        # known-truth data at 17 pulses it is consistently WORSE: hit rate
        # 0.205 +/- 0.012 against 0.256 +/- 0.008 for this sweep over 4 noise
        # seeds, and it introduces a -0.15 to -0.21 bias slope where the sweep
        # has none. It spends pulses 2 and 3 at +/-span, where the contrast is
        # only 1/(1+span^2), so the two least-damped pulses land on the least
        # informative detunings. Keep the sweep unless that is re-measured.
        sample_idx = np.rint(np.linspace(0, m - 1, self.p.N_pulses))
        sample_idx = np.clip(sample_idx, 0, m - 1).astype(int)
        self.p.omega_pulse_list = omega_grid[sample_idx]
        # Callers assign the return value (scan_kernel does so every shot);
        # returning None here would null out the list we just built.
        return self.p.omega_pulse_list

    @kernel
    def per_feedback_loop_top(self, idx):
        self.omega_raman = self.p.omega_pulse_list[idx]

    @kernel
    def per_feedback_loop_end(self, idx):
        """
        Store the probabilities and the frequency mesh at each step. Note the
        use of +1 on the index, this accounts for the first row of each
        corresponding to before the first shot.
        """
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