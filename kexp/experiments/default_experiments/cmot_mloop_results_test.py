from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class cmot_mloop_results_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        self.p.t_tof = 3.e-3
        #self.xvar('t_tof',np.linspace(230.,700.,10)*1.e-6)
        self.xvar('use_mloop_params',[0,1])
        
        self.p.N_repeats = 100

        self.p.t_mot_load = .1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        if self.p.use_mloop_params:
            self.p.detune_push = -3.152
            self.p.amp_push = 0.108
            self.p.detune_d2_c_2dmot = -1.202
            self.p.detune_d2_r_2dmot = -2.933
            self.p.amp_d2_c_2dmot = 0.179
            self.p.amp_d2_r_2dmot = 0.172
            self.p.v_2d_mot_current = 1.968
            self.p.detune_d2_c_mot = -1.599
            self.p.detune_d2_r_mot = -3.918
            self.p.amp_d2_c_mot = 0.2
            self.p.amp_d2_r_mot = 0.099
            self.p.i_mot = 17.403

        self.dds.init_cooling()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)

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