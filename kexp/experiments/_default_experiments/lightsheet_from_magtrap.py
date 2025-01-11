from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('detune_d2_r_d1cmot',np.linspace(-7.,0.,8))
        # self.p.detune_d2_r_d1cmot = -3.88
        # self.xvar('amp_d2_r_d1cmot',np.linspace(.02,.18,8))
        # self.p.amp_d2_r_d1cmot = .065

        # self.xvar('detune_d1_c_d1cmot',np.linspace(3.,10.,8))
        # self.p.detune_d1_c_d1cmot = 7.5
        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(.1,.99,8))
        # self.p.pfrac_d1_c_d1cmot = .86

        # self.xvar('pfrac_d1_c_gm',np.linspace(.2,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.2,.99,8))
        # self.p.pfrac_d1_c_gm = .95
        # self.p.pfrac_d1_r_gm = .95

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.5,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.05,.5,8))
        # self.p.pfrac_c_gmramp_end = 0.115
        # self.p.pfrac_r_gmramp_end = 0.242
        
        # self.p.v_pd_lightsheet_rampup_end = 9.99
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.5,9.99,5))
        # self.xvar('v_lightsheet_paint_amp_max',np.arange(-7.,6.,1))
        # self.xvar('t_lightsheet_rampup',np.linspace(0.05,3.,20))

        # self.xvar('i_magtrap_init',np.linspace(18.,70,8))
        self.p.i_magtrap_init = 28.

        # self.xvar('v_zshim_current_magtrap',np.linspace(.0,3.,10))
        # self.p.v_zshim_current_magtrap = .12
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,1.,10))
        # self.p.v_xshim_current_magtrap = .14
        # self.xvar('v_yshim_current_magtrap',np.linspace(2.,9.,20))
        # self.p.v_yshim_current_gm = 2.545

        # self.xvar('i_magtrap_init',np.linspace(20.,30.,10))

        # self.xvar('i_magtrap_ramp_end',np.linspace(30.,95.,10))

        # self.xvar('t_magtrap_ramp',np.linspace(.05,6.,10))
        self.p.t_magtrap_ramp = .5

        self.p.t_lightsheet_hold = 10.e-3

        self.xvar('t_tof',np.linspace(300.,1000.,10)*1.e-6)
        self.p.t_tof = 800.e-6
        self.p.N_repeats = 1

        self.p.amp_imaging = .25

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet()
        
        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()
    
        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        # self.lightsheet.off()

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