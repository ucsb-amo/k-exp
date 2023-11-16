from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class cmot_d1_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "scan d1 c power"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = 1
        self.p.t_tof = 5000 * 1.e-6 # mot

        self.p.t_d1cmot = np.linspace(1.0,10.0,10) * 1.e-3

        self.xvarnames = ['t_d1cmot']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.t_d1cmot:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(xvar * s)

            # self.gm(self.p.t_gm * s)

            # self.gm_ramp(self.p.t_gm_ramp * s)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")