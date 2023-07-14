from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class oneshot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,absorption_image=False,basler_imaging=True)
        # Base.__init__(self,setup_camera=False)

        self.run_info._run_description = "gm with fluorescence camera"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 1
        self.p.N_repeats = 1
        self.p.t_tof = 100.e-6

        self.p.dummy = np.linspace(1.,1.,self.p.N_shots)

        self.xvarnames = ['dummy']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        self.dds.tweezer.on()
        
        for _ in self.p.dummy:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)
            
            self.cmot_d1(self.p.t_d1cmot * s)
            
            # self.gm(self.p.t_gm * s)
            
            # self.gm_ramp(self.p.t_gm_ramp * s)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.fl_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")