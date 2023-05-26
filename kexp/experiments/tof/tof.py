from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "gm tof with ramp"

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.t_gm_ramp = 5.e-3

        self.p.N_shots = 4
        self.p.N_repeats = 1
        # self.p.t_tof = np.linspace(300,700,self.p.N_shots) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(750,1250,self.p.N_shots) * 1.e-6 # d2 cmot
        self.p.t_tof = np.linspace(1000,3000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(7500,10000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(1000,3000,self.p.N_shots) * 1.e-6 # gm
        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        self.xvarnames = ['t_tof']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t_tof in self.p.t_tof:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            # self.gm(self.p.t_gm * s)

            # self.gm_ramp(self.p.t_gm_ramp * s)
            
            self.release()
            
            ### abs img
            delay(t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")