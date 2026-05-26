
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
        self.p.t_tof = 50.e-6

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)
        
        # self.xvar('t_tweezer_hold', np.linspace(0.,20.,10) * 1.e-6)
        self.t_tweezer_hold = 10.e-3

        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.prepare_hf_tweezers(squeeze=True)

        # delay(-10.)

        self.core.break_realtime()
        
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
