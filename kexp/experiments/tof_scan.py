from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')
        # self.xvar('pfrac_c_gmramp_end',np.linspace(.2,.7,5))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.4,5))

        # self.xvar('pfrac_d1_c_gm',np.linspace(.4,.9,5))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.3,.5,5))

        # self.xvar('t_gm',np.linspace(1.,8.,5)*1.e-3)
        # self.xvar('t_gmramp',np.linspace(3.,9.,5)*1.e-3)

        # self.xvar('detune_push',np.linspace(-4.,4.,5))
        # self.xvar('amp_push',np.linspace(.05,.188,5))

        # self.xvar('detune_d2_c_mot',np.linspace(-3.,0.,5))
        # self.xvar('detune_d2_r_mot',np.linspace(-5.,-3.,5))
        self.xvar('i_mot',np.linspace(22.,25.,5))

        self.xvar('t_tof',np.linspace(10000,16000,5)*1.e-6)

        self.p.t_mot_load = 1.
        self.p.t_tof = 12000.e-6
        # self.p.t_gm = 3.e-3
        # self.p.t_gmramp = 4.e-3


        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=.84, v_yshim_current=self.p.v_yshim_current, v_xshim_current=self.p.v_xshim_current)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)
        self.release()
        
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup,with_painting=True)
        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


