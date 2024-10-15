from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('detune_d1_c_d1cmot',np.linspace(0.,10.,10))

        # self.xvar('detune_d1_c_gm',np.linspace(7.,11.,8))
        # self.p.detune_d1_c_gm = 10.14
        # self.xvar('detune_d1_r_gm',np.linspace(7.,11.,8))
        # self.p.detune_d1_r_gm = 9.571
        self.p.detune_gm = 7.85
        # self.xvar('detune_gm',np.linspace(7.,10.,8))

        # self.xvar('pfrac_d1_c_gm',np.linspace(.2,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.2,.99,8))
        # self.p.pfrac_d1_c_gm = .7
        # self.p.pfrac_d1_r_gm = .7

        self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.6,8))
        self.xvar('pfrac_r_gmramp_end',np.linspace(.05,.6,8))
        # self.p.pfrac_c_gmramp_end = 0.15
        # self.p.pfrac_r_gmramp_end = 0.05
        # self.xvar('pfrac_gm',np.linspace(0.2,0.9,8))

        # self.xvar('v_zshim_current_gm',np.linspace(0.,2.,8))
        # self.xvar('v_xshim_current_gm',np.linspace(0.,2.,8))
        # self.xvar('v_yshim_current_gm',np.linspace(0.,3.,8))

        # self.p.v_yshim_current_gm = 1.2
        # self.xvar('dumdum',[0]*100)

        # self.xvar('t_tof',np.linspace(13.,18.,10)*1.e-3)
        
        self.p.imaging_state = 2.
        self.p.t_tof = 16.e-3
        self.p.t_mot_load = 0.1
        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.p.pfrac_d1_c_gm = self.p.pfrac_gm
        # self.p.pfrac_d1_r_gm = self.p.pfrac_gm / 3
        
        self.switch_d2_2d(1)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

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