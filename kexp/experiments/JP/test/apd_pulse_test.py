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
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.N_repeats = 1

        self.p.amplitude_imaging = 0.2

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        if self.p.amplitude_imaging != 0.:
            self.imaging.set_power(self.p.amplitude_imaging)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.imaging.on()
        delay(200.e-3)
        self.imaging.off()
        
        

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep([0])
        self.core.break_realtime()
        delay(30.e-3)

        delay(2.)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)