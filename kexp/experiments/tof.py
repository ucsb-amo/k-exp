from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        N = 7
        self.p.N_repeats = 1

        # self.p.t_tof = np.linspace(1000,1500,N) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(2000,3500,N) * 1.e-6 # cmot
        # self.p.t_tof = np.linspace(4000,6000,N) * 1.e-6 # d1 cmot
        self.p.t_tof = np.linspace(6000,9000,N) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(8000,13000,N)  * 1.e-6 # gm
        # self.p.t_tof = np.linspace(9023,13368,N) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(20,100,N) * 1.e-6 # tweezer
        # self.p.t_tof = np.linspace(20,100,N) * 1.e-6 # mot_reload

        # self.p.frequency_detuned_imaging_F1 = self.p.frequency_detuned_imaging + 461.7e6

        self.ttl.ttl_trig = self.get_device("ttl14")

        self.xvarnames = ['t_tof']

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for t_tof in self.p.t_tof:

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()

            # self.cmot_d2(self.p.t_d2cmot * s)

            self.cmot_d1(self.p.t_d1cmot * s)

            # self.ttl.ttl_trig.on()
            self.gm(self.p.t_gm * s)

            self.gm_ramp(self.p.t_gmramp * s)
            # self.ttl.ttl_trig.off()

            self.release()

            ### abs img
            delay(t_tof * s)
            # self.fl_image()
            # self.flash_repump()
            self.abs_image()

            self.core.break_realtime()
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")