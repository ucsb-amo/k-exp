from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 2.

        self.xvar('dummy',[0]*1000)

        self.p.t_mot_load = 1.

        self.finish_build()

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm, v_yshim_current=self.p.v_yshim_current_gm, v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.flash_repump()
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

