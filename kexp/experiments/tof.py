from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 15. * 1.e-3

        self.p.t_andor_expose = 50. * 1.e-3

        self.p.N_shots = 5
        self.p.N_repeats = 1
        self.p.t_tof = np.linspace(100,400,self.p.N_shots) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(400,1250,self.p.N_shots) * 1.e-6 # cmot
        # self.p.t_tof = np.linspace(1000,2000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(10000,15000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(1200,2400,self.p.N_shots) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # mot_reload

        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        self.xvarnames = ['t_tof']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t_tof in self.p.t_tof:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            # self.cmot_d1(self.p.t_d1cmot * s)

            # self.dds.tweezer.on()

            # self.gm(self.p.t_gm * s)

            # self.switch_d1_3d(0)

            # self.gm_ramp(self.p.t_gm_ramp * s)

            # self.tweezer_trap(self.p.t_tweezer_hold)

            # self.dds.tweezer.off()

            # delay(self.p.t_tweezer_hold)

            # self.mot_reload(self.p.t_mot_reload * s)
            
            self.release()
            
            ### abs img
            delay(t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")