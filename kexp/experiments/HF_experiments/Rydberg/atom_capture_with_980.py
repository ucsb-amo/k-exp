
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(5.,20.,10)*1.e-3)
        self.p.t_tof = 15.e-3

        # self.xvar('turn_on_980',[0,1])
        self.p.turn_on_980 = 1

        self.p.N_repeats = 10

        self.p.t_mot_load = 0.5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        if self.p.turn_on_980:
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
        delay(3.e-6)
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
