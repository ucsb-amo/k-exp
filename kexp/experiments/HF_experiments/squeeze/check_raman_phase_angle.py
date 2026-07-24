from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

from kexp.experiments.HF_experiments.squeeze.expt_params_squeezing import ExptParams

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        self.p = ExptParams()
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      expt_params=self.p,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 2

        self.p.t_tweezer_hold = 2.e-3
        
        self.p.N_repeats = 1

        self.xvar('step_phase',[0,1])

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # set up squeeze img
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers(squeeze=False)
        self.prep_raman(phase_mode=1)

        self.raman.pulse(self.p.t_raman_pulse) # prepare x SCS

        if self.p.step_phase:
            self.raman.set_phase(np.pi/2)

        self.raman.pulse(self.p.t_raman_pulse)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        self.abs_image()
        

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)