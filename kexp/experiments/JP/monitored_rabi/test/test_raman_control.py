from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class test_raman_control(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.xvar('flip_raman_rotation_axis',[0,1])

        self.p.t_tof = 1000.e-6
        self.p.N_repeats = 5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.raman.pulse(self.p.t_raman_pi_pulse / 2)
        delay(10.e-6)
        if self.p.flip_raman_rotation_axis:
            self.raman.set_phase(np.pi/2)
        else:
            pass
        delay(10.e-6)
        self.raman.pulse(self.p.t_raman_pi_pulse / 2)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)