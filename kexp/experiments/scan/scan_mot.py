from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class scan_mot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "optimize mot detunings"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 5
        self.p.N_repeats = 1

        self.p.t_tof = 200.e-6

        self.p.xvar1_detune_d2_c_mot = np.linspace(-1.,1.,self.p.N_shots)
        self.p.xvar2_detune_d2_r_mot = np.linspace(-5.,-3.,self.p.N_shots)

        self.xvarnames = ['xvar1_detune_d2_c_mot','xvar2_detune_d2_r_mot']

        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for detune_c in self.p.xvar1_detune_d2_c_mot:
            for detune_r in self.p.xvar2_detune_d2_r_mot:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s, detune_d2_c=detune_c, detune_d2_r=detune_r)

                self.release()

                delay(self.p.t_tof)

                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.p.detune_d2_c_mot = self.p.xvar1_detune_d2_c_mot
        self.p.detune_d2_r_mot = self.p.xvar2_detune_d2_r_mot

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")