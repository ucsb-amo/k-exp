from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)
        self.camera_params.serial_no = camera_params.basler_fluor_camera_params.serial_no
        self.camera_params.magnification = camera_params.basler_fluor_camera_params.magnification

        self.run_info._run_description = "compare gm health with 2d mot on vs 2d mot off"

        ## Parameters

        self.p = self.params

        self.p.t_tof = np.linspace(8000,10000,6) * 1.e-6 # gm
        self.p.state_2dmot_bool = np.array([0,1])

        self.xvarnames = ['state_2dmot_bool','t_tof']
        self.p.N_repeats = [2,1]

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for state_2dmot_bool in self.p.state_2dmot_bool:
            for t_tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)
                # self.hybrid_mot(self.p.t_mot_load * s)

                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                self.dds.push.off()
                if state_2dmot_bool:
                    self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.gm(self.p.t_gm * s)

                self.release()

                ### abs img
                delay(t_tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

                if not state_2dmot_bool:
                    self.switch_d2_2d(0)
                    delay(1*s)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")