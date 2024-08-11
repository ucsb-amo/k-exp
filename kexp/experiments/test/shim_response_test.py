from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class pumping_flash_calibration(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False,camera_select='xy_basler',save_data=False)

        self.xvar('x',[0])
        self.p.N_repeats = 1000

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_shims(v_xshim_current=self.p.v_xshim_current_gm,
                       v_yshim_current=self.p.v_yshim_current_gm,
                       v_zshim_current=self.p.v_zshim_current_gm)
        delay(100.e-3)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.set_shims(v_xshim_current=self.p.v_xshim_current_op,
                       v_yshim_current=self.p.v_yshim_current_op,
                       v_zshim_current=self.p.v_zshim_current_op)
        
        delay(100.e-3)

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