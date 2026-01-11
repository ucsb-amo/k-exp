from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION)

        self.p.frequency_raman_transition = 145.57e6 # 191. A
        # self.p.frequency_raman_transition = 147.24e6 # 182. A

        # self.xvar('fraction_power_raman',np.linspace(0., 0.5, 10))
        self.p.fraction_power_raman = .5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.ttl.raman_shutter.on()
        delay(5.e-3)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.raman.on()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)