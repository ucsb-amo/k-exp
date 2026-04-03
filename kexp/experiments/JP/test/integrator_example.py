from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu, at_mu

class integrator_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_img_pulse = 3.e-6

        self.p.amplitude_imaging = 0.5
        
        self.p.N_repeats = 1

        self.p.N_pulses = 10000
        self.data.apd = self.data.add_data_container(self.p.N_pulses) # set up data container w/ # data points per shot
        # access data in loaded atomdata as ad.data.apd

        self.camera_params.gain = 1 # if you really don't care about images and to avoid killing camera

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.integrator.init() # init the integrator

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amplitude_imaging)

        delay(10.e-3)

        self.ttl.pd_scope_trig3.pulse(1.e-8)

        for i in range(self.p.N_pulses):
            # take an imaging pulse and store it in the data container at index i for this shot
            self.integrated_imaging_pulse(
                                    self.data.apd,
                                    t = self.p.t_img_pulse,
                                    dark = False,
                                    idx = i)

        delay(10.e-3)

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep([0,2,3])
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)