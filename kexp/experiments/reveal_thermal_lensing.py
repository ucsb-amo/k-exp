from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class thermal_lensing(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='z_basler',save_data=True)

        self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(0.5,4.0,10))
        # self.xvar('t_lightsheet_hold',np.linspace(10.,315.,30)*1.e-3)
        
        self.p.t_lightsheet_rampup = 10.e-3
        self.p.t_lightsheet_hold = 315.e-3

        self.p.N_repeats = 1

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        delay(1.0)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_lightsheet_hold)
        self.abs_image()
        self.lightsheet.off()


    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
        self.mot_observe(i_supply=self.p.i_mot)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


