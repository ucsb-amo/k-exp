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
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      expt_params=self.p,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_raman_pulse = 0.

        self.p.t_tweezer_hold = 2.e-3

        self.xvar('t_squeeze_img_pulse',np.linspace(0.5,10.,10)*1.e-6)
        self.p.t_measurement_pulse = 20.e-6
        self.p.amp_imaging = 0.1
        
        self.p.N_repeats = 30

        self.data.apd = self.data.add_data_container(1)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up squeeze img
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=False)
        self.prep_raman(phase_mode=1)

        self.raman.pulse(self.p.t_raman_pulse) # rotate pi/2 on y axis -- prepare x SCS
        self.imaging.pulse(self.p.t_squeeze_img_pulse) # squeeze
        self.raman.set_phase(np.pi/2) # next rotation about x axis -- puts increased variance along z
        self.raman.pulse(self.p.t_squeeze_img_pulse) # rotate pi/2 on x axis

        # readout
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.integrated_imaging_pulse(data_container=self.data.apd,
                                              t=self.p.t_measurement_pulse)
        delay(10.e-6)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)