"""check_rabi_frequency_apd with the Raman pulse done by the OPX.

Same shot as HF_experiments/feedback/calibrations/check_rabi_frequency_apd.py
-- tweezer prep, one Raman exposure of t_raman_pulse, then the usual 3-point
integrated APD readout (atoms / no-atoms / dark) on the ARTIQ side -- except
the Raman pulse is played by the OPX (kexp.control.opx, sequence
rabi_raman_pulse): ARTIQ hands off, the OPX gates the common Raman switch
AOM open for t_raman_pulse (delivered per shot from the scan table), and
hands back.

prep_raman() stays, unchanged from the reference: its 3 ms warm-up pulse
thermally loads the common switch AOM -- the very AOM the OPX gates -- and
runs while the shutter is still closed, so the warm-up light never reaches
the atoms; only then does it open the shutter. The OPX sticky analog drives
cover a different thing entirely (the 80/150 double-pass AOs, whose servo
must never see the RF drop) and are no substitute for the switch-AOM
warm-up. The only line that changes is raman.pulse -> handoff/handback.

Readout is unchanged ARTIQ (integrator APD), so this flop compares directly
against check_rabi_frequency_apd runs at the same settings.

*** NOT YET RUN ON HARDWARE (milestone M2). Verify the handshake on a scope
(milestone M1) before running this with atoms. ***
"""

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback
from kexp.experiments.opx_sequences.rabi import rabi_raman_pulse

class hf_raman_opx(EnvExperiment, Base):

    def prepare(self):
        p = ExptParamsFeedback()
        Base.__init__(self,camera_select=cameras.apd,
                      save_data=True,
                      expt_params=p,
                      imaging_type=img_types.DISPERSIVE)

        self.xvar('t_raman_pulse', np.linspace(0.,50.,20)*1.e-6)

        self.p.t_raman_pulse = 0.

        self.p.t_tweezer_hold = 2.e-3

        self.data.apd = self.data.add_data_container(3)

        self.p.t_tof = 800.e-6

        self.p.N_repeats = 1

        self.opx.use(rabi_raman_pulse)
        # self.opx.use(rabi_raman_pulse, simulate=True)  # waveform report, no run

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        # warm-up (switch AOM, shutter closed) + shutter open + line-trigger
        # sync, exactly as in the reference; only the pulse moves to the OPX
        self.prep_raman()

        self.handoff_to_quantum_machines()
        self.wait_for_quantum_machines_handoff()

        self.ttl.raman_shutter.off()

        self.imaging.integrated_imaging_pulse(self.data.apd, t=self.p.t_img_pulse, idx=0)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(10.e-3)

        self.imaging.integrated_imaging_pulse(self.data.apd, t=self.p.t_img_pulse, idx=1)

        delay(50.e-6)

        self.imaging.integrated_imaging_pulse(self.data.apd, t=self.p.t_img_pulse, idx=2, dark=True)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
