from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu, at_mu

class test_scope(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.camera_params.amp_imaging = 0.25
        self.p.t_img_pulse = 10.e-6
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)
        self.core.break_realtime()

        self.ttl.pd_scope_trig3.pulse(1.e-8)

        self.imaging.pulse(self.p.t_img_pulse)

        delay(10.e-3)

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep([0,1])
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