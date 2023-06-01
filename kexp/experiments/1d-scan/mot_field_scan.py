from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class mot_field_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "scan mot gradient"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 6
        self.p.N_repeats = 1
        self.p.t_tof = 500 * 1.e-6 # mot

        self.p.xvar_v_mot_current = np.linspace(0.8,1.6,self.p.N_shots)
        self.p.xvar_v_mot_current = np.repeat(self.p.xvar_v_mot_current,self.p.N_repeats)

        self.xvarnames = ['xvar_v_mot_current']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_v_mot_current:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s, v_current=xvar)
            # self.hybrid_mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)

            # self.cmot_d1(self.p.t_d1cmot * s)

            # self.gm(self.p.t_gm * s)

            # self.gm_ramp(self.p.t_gm_ramp * s)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):
        
        self.p.v_mot_current = self.p.xvar_v_mot_current

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")