from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class gm_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "GM scan"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000,8000,5) * 1.e-6
        self.p.t_tof = 11000.e-6

        # self.p.xvar_detune_gm = np.linspace(1.,5.,self.p.N_shots)
        self.p.xvar_t_gm = np.linspace(8.,15.,6) * 1.e-3

        # self.xvarnames = ['xvar_detune_gm']
        self.xvarnames = ['xvar_t_gm']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t_gm in self.p.xvar_t_gm:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)

            self.dds.push.off() 
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d2cmot * s)

            self.gm(t_gm * s)

            # self.gm_ramp(self.p.t_gm_ramp)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
