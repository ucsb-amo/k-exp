from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 1.

        # self.xvar('t_tof',np.linspace(13.,19.,10)*1.e-3)

        self.p.t_tof = 13.e-3

        self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.4,5))
        self.xvar('pfrac_r_gmramp_end',np.linspace(.03,.4,4))

        self.p.N_repeats = [2,3]

        self.p.t_mot_load = .4

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)

        self.gm(self.p.t_gm * s)
        self.ttl.pd_scope_trig.on()
        self.gm_ramp(self.p.t_gmramp)
        self.ttl.pd_scope_trig.off()

        self.release()

        delay(self.p.t_tof)
        # self.flash_repump()
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