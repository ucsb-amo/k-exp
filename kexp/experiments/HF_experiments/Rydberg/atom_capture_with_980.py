
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(20.,100.,7)*1.e-6)
        self.p.t_tof = 80.e-6

        # self.xvar('wee',[1,0])
        self.p.wee = 1

        self.xvar('frequency_eo_980', np.arange(137.,149.,1)*1.e6)
        # self.p.frequency_eo_980 = 139*1.e6

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)
        
        # self.xvar('t_tweezer_hold', np.linspace(0.,75.,15) * 1.e-3)
        self.t_tweezer_hold = 3.e-3

        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.ry_980.set_siglent(self.p.frequency_eo_980)

        self.ry_980.on()
        self.ry_405.on()
        delay(100.e-3)
        self.ry_405.off()
        self.ry_980.off()

        self.ry_980.on()

        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.cmot_d1(self.p.t_d1cmot)

        self.ttl.pd_scope_trig.pulse(1.e-8)
        self.gm(self.p.t_gm)
        self.gm_ramp(self.p.t_gmramp)

        self.release()
        delay(self.p.t_tof)
        self.ry_980.off()
        delay(100.e-6)
        self.flash_repump()
        self.abs_image()
        

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
