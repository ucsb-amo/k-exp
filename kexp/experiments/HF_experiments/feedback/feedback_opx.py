"""Bayesian frequency feedback with the per-pulse loop on the OPX.

The feedback_fast.py shot with feedback_loop moved off the ARTIQ kernel:
ARTIQ prepares the tweezer ensemble, warms the switch AOM (prep_raman) and
hands off; the OPX runs N_pulses cycles of [random-duration Raman pulse at
the posterior's drive] -> [5 us imaging exposure integrated on the APD] ->
[posterior update in QUA fixed point] -> [next drive] (sequence
kexp.experiments.opx_sequences.feedback.bayesian_feedback) and hands back;
ARTIQ then holds, drops the trap and takes the TOF image as before.

Phase model: "reset" -- both Raman drives are phase-reset at the align in
front of every pulse, so the two-photon drive phase at pulse start is 0
and the atom-drive phase advances at the transition frequency between
pulses (0.478 turns per 4 ns cycle). Every per-step interval is computed
on the host from the drawn pulse-time list, the OPX is held to it with a
per-step wait, and every pulse start is timestamped; see the sequence
module and expt_params_feedback_opx.py. The drive of every pulse is a
grid index (the next drive is the posterior argmax; the initial drive is
the grid point nearest feedback_fractional_initial_offset) applied as
the grid point's integer-Hz IFs on both AOs from a host table, so the
analysis knows the applied two-photon frequency exactly (drive_index +
if_table_hz -> omega_raman).

Data (the minimal set the replay needs): the ARTIQ container names are
kept (apd, omega_raman, s_z, t, probabilities, omega_raman_mesh,
t_raman_pulse, t_raman_pulse_seed) plus the OPX's log weights
(log_weights, scale feedback_log_weight_scale), the drive index
(drive_index), the run's integer IF table (if_table_hz) and the
pulse-start timestamps (t_pulse_start_cc -> t_pulse_start). Analysis:
kexp.analysis.FeedbackOPXReplay.

*** NOT YET RUN ON HARDWARE. Prerequisites, in order:
  M1  the ARTIQ <-> OPX handshake on a scope (trigger -> block latency vs
      the 350 ns t_opx_handoff_artiq_side assumption; hand-back slack).
  M2  an OPX-driven Rabi flop (experiments/qm/check_rabi_frequency_apd_opx.py):
      the OPX drives the AOs at the dds defaults, not ARTIQ's sqrt(0.3)
      scaling, so t_raman_pi_pulse must be re-measured for the OPX drive,
      and t_raman_pulse_offset_opx (switch-path turn-on latency) with it.
  M3  the APD readout in OPX units: demod2volts convention (factor 2),
      time_of_flight, and the S_z endpoint calibration v_apd_all_up_opx /
      v_apd_all_down_opx + std_photon_fraction_opx through the OPX measure
      (calibrations/apd_voltage_vs_state_2.py with the OPX playing the
      pulses; apd_pulse_analysis_measured_pi.ipynb).
  Also to be measured on the simulator/hardware from the timestamp streams:
  the per-cycle align overhead (t_opx_feedback_align_overhead) and the
  posterior compute time, which sets t_opx_feedback_compute_budget. ***
"""

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

from kexp.experiments.HF_experiments.feedback.expt_params_feedback_opx import ExptParams as ExptParamsFeedbackOPX
from kexp.experiments.opx_sequences.feedback import bayesian_feedback


class feedback_opx(EnvExperiment, Base):

    def prepare(self):
        p = ExptParamsFeedbackOPX()
        Base.__init__(self,
                      camera_select=cameras.apd,
                      imaging_type=img_types.DISPERSIVE,
                      expt_params=p,
                      save_data=True,
                      save_on_underflow=True)

        # closed loop: the posterior on the OPX picks every drive (the
        # sequence refuses to trace if this disagrees with the mode)
        self.p.update_raman_frequency_bool = 1
        self.p.include_photon_noise = 1

        ### parameters (as feedback_fast.py)
        self.p.feedback_fractional_initial_offset = 2.
        # self.xvar('feedback_fractional_initial_offset', np.linspace(0., 4., 5))

        self.p.N_repeats = 21
        self.p.N_pulses = 17            # number of steps of evolution
        self.p.feedback_guess_span_Omega = 3.

        # pinned seed = every shot replays the same pulse-time list; 0 draws
        # a fresh seed per shot (recorded in data.t_raman_pulse_seed)
        # self.p.t_raman_pulse_seed = 0
        # self.xvar('t_raman_pulse_seed', np.arange(1, 22))

        # per-cycle budget for readback + posterior (see the params file);
        # tighten once the compute time is measured
        # self.p.t_opx_feedback_compute_budget = 40.e-6

        self.opx.use(bayesian_feedback)
        # self.opx.use(bayesian_feedback, simulate=True)   # waveform report, no run

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        # warm-up (switch AOM, shutter closed) + shutter open + line-trigger
        # sync, exactly as the ARTIQ loop; the drives are pointed at the
        # transition so the OPX's IFs match what prep_raman set
        self.prep_raman(frequency_transition=self.p.frequency_raman_transition,
                        phase_mode=0)

        # the whole pulse train runs on the OPX between these two calls
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
