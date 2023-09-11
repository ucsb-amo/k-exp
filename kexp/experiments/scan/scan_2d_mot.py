from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class scan_2d_mot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "optimize 2d mot detunings"

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 2

        self.p.N_shots = 4
        self.p.N_repeats = 1

        self.p.t_tof = 2000.e-6

        self.p.xvar_detune_d2_c_2dmot = np.linspace(-0.4,0.8,self.p.N_shots)
        self.p.xvar_detune_d2_r_2dmot = np.linspace(-3.,-2.6,self.p.N_shots)

        # self.p.xvar_amp_d2_c_2dmot = np.linspace(.1,.2,self.p.N_shots)
        # self.p.xvar_amp_d2_r_2dmot = np.linspace(.1,.2,self.p.N_shots)

        self.xvarnames = ['xvar_detune_d2_c_2dmot','xvar_detune_d2_r_2dmot']
        
        # self.xvarnames = ['xvar_amp_d2_c_2dmot','xvar_amp_d2_r_2dmot']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar1 in self.p.xvar_detune_d2_c_2dmot:
            for xvar2 in self.p.xvar_detune_d2_r_2dmot:
                # self.load_2D_mot(self.p.t_2D_mot_load_delay * s,
                #                  amp_d2_c=xvar1, amp_d2_r=xvar2)
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s,
                                 detune_d2_c=xvar1, detune_d2_r=xvar2)

                self.mot(self.p.t_mot_load * s)

                self.release()

                delay(self.p.t_tof)

                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.p.detune_d2_c_2dmot = self.p.xvar_detune_d2_c_2dmot
        self.p.detune_d2_r_2dmot = self.p.xvar_detune_d2_r_2dmot
        
        # self.p.amp_d2_c_2dmot = self.p.xvar_amp_d2_c_2dmot
        # self.p.amp_d2_r_2dmot = self.p.xvar_amp_d2_r_2dmot

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")