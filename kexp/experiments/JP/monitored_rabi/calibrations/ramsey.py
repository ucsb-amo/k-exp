from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class ramsey(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_raman_transition', 147.2521e6 + np.linspace(-2.,2,5)*1.e3)
        # self.xvar('frequency_raman_transition', self.p.frequency_raman_transition + np.arange(-20.,20.,1.)*1.e3)
        self.xvar('frequency_raman_transition', 147.26e6 + np.arange(-3.,3.,1.)*1.e3)
        self.xvar('t_ramsey',np.linspace(0.,100.,15)*1.e-6)
        # self.p.t_ramsey = 40.e-6

        self.p.t_tof = 10.e-6
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.tweezer_squeeze()
        self.prep_raman()

        self.raman.pulse(self.p.t_raman_pi_pulse/2)
        delay(self.p.t_ramsey)
        self.raman.pulse(self.p.t_raman_pi_pulse/2)

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

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)