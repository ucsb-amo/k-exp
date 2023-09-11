from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class mot_load_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "scan mot load"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 8
        self.p.N_repeats = 3
        self.p.t_tof = 800 * 1.e-6 # mot

        self.p.xvar_t_mot_load = np.linspace(0.1,3.5,self.p.N_shots)

        self.xvarnames = ['xvar_t_mot_load']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_t_mot_load:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(xvar * s)

            self.dds.push.off()
            self.switch_d2_2d(0)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):
        
        self.p.t_mot_load = self.p.xvar_t_mot_load

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")