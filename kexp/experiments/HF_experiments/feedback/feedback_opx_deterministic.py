"""Open-loop grid sweep of the OPX feedback loop (deterministic_bayesian.py
on the OPX).

Same shot as feedback_opx.py, but the drive frequency of pulse i is the
grid point rint(linspace(0, m-1, N_pulses))[i] of the shot's hypothesis
grid -- the monotonic sweep of deterministic_bayesian.get_new_pulse_list --
while the posterior still runs on the OPX and is saved every pulse. The
schedule is computed on the host at trace time from the same grid the OPX
carries (kexp.experiments.opx_sequences.feedback.open_loop_drive_indices,
recomputable from omega_raman_mesh); what the OPX actually drove is in
data.drive_index (the grid index) and data.omega_raman (rad/s, from the
index and the run's integer IF table if_table_hz).

Scanning feedback_fractional_initial_offset moves WHICH grid index sits on
resonance (the grid snaps onto resonance, see feedback_grid_omega), so as
in the ARTIQ experiment the thing scanned is where the truth sits in the
prior. The grid is rebuilt per shot on the host for that scan.

*** NOT YET RUN ON HARDWARE -- prerequisites M1-M3 as in feedback_opx.py. ***
"""

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

from kexp.experiments.HF_experiments.feedback.expt_params_feedback_opx import ExptParams as ExptParamsFeedbackOPX
from kexp.experiments.opx_sequences.feedback import bayesian_feedback_open_loop


class feedback_opx_deterministic(EnvExperiment, Base):

    def prepare(self):
        p = ExptParamsFeedbackOPX()
        Base.__init__(self,
                      camera_select=cameras.apd,
                      imaging_type=img_types.DISPERSIVE,
                      expt_params=p,
                      save_data=True,
                      save_on_underflow=True)

        # open loop: the drive follows the host schedule, the posterior only
        # watches (the sequence refuses to trace if this disagrees)
        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.N_repeats = 21
        self.p.N_pulses = 9             # number of steps of evolution

        ### parameters (as deterministic_bayesian.py)
        # feedback_guess_span_Omega is a HALF-width: span 2 at 21 points is
        # a grid step of 0.2 Omega
        self.p.feedback_grid_size = 21
        self.p.feedback_guess_span_Omega = 2.0

        # slide the resonance across the grid: 5 offsets over the full
        # width land it on indices 0, 5, 10, 15, 20
        self.p.feedback_fractional_initial_offset = 0.
        # self.xvar('feedback_fractional_initial_offset',
        #           np.linspace(-self.p.feedback_guess_span_Omega,
        #                       self.p.feedback_guess_span_Omega, 5))

        self.opx.use(bayesian_feedback_open_loop)
        # self.opx.use(bayesian_feedback_open_loop, simulate=True)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_transition=self.p.frequency_raman_transition,
                        phase_mode=0)

        self.handoff_to_quantum_machines()
        self.wait_for_quantum_machines_handback()

        delay(self.p.t_tweezer_hold)
        self.ttl.raman_shutter.off()

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
