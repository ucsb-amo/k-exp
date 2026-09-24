"""qm_rabi_frequency rebuilt on the OPX program builder (kexp.control.opx).

Same physics as qm_rabi_frequency.py, but instead of running the OPX
program by hand on the side (customer-weld-ucsb/experiments/00d), the
framework compiles and launches it at finish_prepare: one job looping over
all shots, t_raman_pulse delivered per shot in the shuffled scan order.
Readout stays ARTIQ's Andor absorption image, so the result compares
directly against both the manual-OPX and the ARTIQ-native raman.pulse
versions of the flop.

*** NOT YET RUN ON HARDWARE (milestone M2). Verify the handshake on a scope
(milestone M1) before running this with atoms. ***
"""

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

from kexp.experiments.opx_sequences.rabi import rabi_raman_pulse

class hf_raman_opx(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        # self.p.t_raman_pulse = 0.
        # self.xvar('t_raman_pulse', np.linspace(0.,30.,15)*1.e-6)
        self.xvar('t_raman_pulse', [0., self.p.t_raman_pi_pulse])

        self.p.t_tweezer_hold = 100.e-3
        self.p.t_tof = 2.0e-3
        self.p.N_repeats = 1

        self.opx.use(rabi_raman_pulse)
        # self.opx.use(rabi_raman_pulse, simulate=True)  # waveform report, no run

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.handoff_to_quantum_machines()
        self.wait_for_quantum_machines_handoff()

        delay(10.e-3)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan(raise_underflow=True)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
