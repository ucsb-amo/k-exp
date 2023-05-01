from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class gm_ramp_tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "optimize 2d mot detunings"

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.N_shots = 6
        self.p.N_repeats = 1

        self.p.t_tof = 500.e-6

        self.p.detune_d2_c_2dmot = np.linspace(-1.,5.,self.p.N_shots)
        self.p.detune_d2_r_2dmot = np.linspace(-1.,5.,self.p.N_shots)

        self.xvarnames = ['detune_d2_c_2dmot','detune_d2_r_2dmot']

        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for detune_c in self.p.detune_d2_c_2dmot:
            for detune_r in self.p.detune_d2_r_2dmot:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s,
                                 detune_d2_c=detune_c, detune_d2_r=detune_r)

                self.mot(self.p.t_mot_load * s)

                delay(self.p.t_tof)

                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")