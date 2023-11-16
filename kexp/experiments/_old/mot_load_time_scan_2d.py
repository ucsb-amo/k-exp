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

        self.p.N_repeats = 1
        self.p.t_tof = np.linspace(1200,1800,6) * 1.e-6

        # self.p.xvar_t_mot_load = np.linspace(0.1,3.5,7)
        self.p.xvar_t_2dmot_load = np.linspace(0.0,1.0,7)

        self.xvarnames = ['xvar_t_2dmot_load','t_tof']

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_t_2dmot_load:
            for t_tof in self.p.t_tof:
                delay(xvar)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()

                # self.cmot_d1(self.p.t_d1cmot * s)

                # self.gm(self.p.t_gm * s)

                # self.gm_ramp(self.p.t_gmramp * s)
                
                self.release()
                
                ### abs img
                delay(t_tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")