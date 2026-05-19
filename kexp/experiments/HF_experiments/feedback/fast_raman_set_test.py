from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
 
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 2

        self.p.t_tweezer_hold = .01e-3

        self.p.t_tof = 90.e-6
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(phase_mode=0)

        self.raman.set_up_fast_frequency_update(aggressive=1)
        self.raman.stage_ffua()

        self.raman.set_frequency_fast(self.p.frequency_raman_transition)

        delay(1.e-6)

        self.raman.pulse(self.p.t_raman_pi_pulse)

        

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        self.raman.clean_up_fast_frequency_update()
        self.ttl.raman_shutter.off()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)