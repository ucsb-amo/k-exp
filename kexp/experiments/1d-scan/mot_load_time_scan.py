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

        self.p.N_repeats = 2
        self.p.t_tof = 12000 * 1.e-6 # mot

        self.p.xvar_t_mot_load = np.linspace(0.1,3.5,7)
        # self.p.xvar_t_2dmot_load = np.linspace(0.1,1.,4)
        # self.p.xvar_t_2dmot_load = np.insert(self.p.xvar_t_2dmot_load,0,0.)
        # self.p.xvar_t_2dmot_load = np.insert(self.p.xvar_t_2dmot_load,3,0.)
        # self.p.xvar_t_mot_kill = np.linspace(.1,3.,10)

        self.xvarnames = ['xvar_t_mot_load']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for t in self.p.xvar_t_mot_load:
        
            self.mot(t * s)

            self.dds.push.off()

            self.cmot_d1(self.p.t_d1cmot * s)

            self.gm(self.p.t_gm * s)

            self.gm_ramp(self.p.t_gmramp * s)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")