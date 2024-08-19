from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class bring_magtrap_to_gm(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.camera_params.amp_imaging = 0.5

        self.p.t_magtrap = 50.e-3
        # self.xvar('t_tof',np.linspace(10.,7000.,15)*1.e-6)
        # self.xvar('t_magtrap',np.linspace(15.,1000.,5)*1.e-3)

        # self.xvar('beans',[0,1])

        # self.xvar("i_outer_magtrap", np.linspace(0.,1.,20))
        # self.xvar("t_tof", np.linspace(10.,500,20)*1.e-6) 
        self.xvar('v_zshim_current',np.linspace(0.1,0.6,10))

        self.p.t_mot_load = 0.3
        
        self.p.N_repeats = 10

        self.p.t_tof = 5.e-3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap()
        delay(self.p.t_magtrap)
        self.inner_coil.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        self.outer_coil.discharge()

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