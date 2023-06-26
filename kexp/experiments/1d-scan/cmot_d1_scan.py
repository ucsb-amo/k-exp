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

        self.p.N_shots = 10
        self.p.N_repeats = 1
        self.p.t_tof = 1000 * 1.e-6 # mot

        self.p.xvar_v_pd_d1_c_d1cmot = np.linspace(2.95,3.15,self.p.N_shots)
        self.p.xvar_v_pd_d1_c_d1cmot = np.repeat(self.p.xvar_v_pd_d1_c_d1cmot,self.p.N_repeats)

        self.xvarnames = ['xvar_v_pd_d1_c_d1cmot']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_v_pd_d1_c_d1cmot:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s, v_pd_d1_c=xvar)

            # self.gm(self.p.t_gm * s)

            # self.gm_ramp(self.p.t_gm_ramp * s)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):
        
        self.p.v_pd_d1_c_d1cmot = self.p.xvar_v_pd_d1_c_d1cmot

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")