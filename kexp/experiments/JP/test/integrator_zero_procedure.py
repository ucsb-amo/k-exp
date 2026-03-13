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
        Base.__init__(self,setup_camera=False,save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        # self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        for _ in range(10000):

            delay(100.e-6)

            self.ttl.pd_scope_trig3.pulse(1.e-8)
            self.integrator.begin_integrate()

            delay(100.e-6)

            self.integrator.ttl_integrate.on()
            delay(10.e-6)
            self.integrator.ttl_reset.off()

        # self.abs_image()

        # self.core.wait_until_mu(now_mu())
        # self.scope.read_sweep([0,3])
        # self.core.break_realtime()
        # delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)