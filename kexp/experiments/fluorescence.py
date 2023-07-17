from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

from kexp.config import camera_params

class flourescence(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,andor_imaging=True)

        self.run_info._run_description = "oneshot"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 50. * 1.e-3

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.start_triggered_grab()
        delay(self.p.t_grab_start_wait)

        self.kill_mot(self.p.t_mot_kill * s)
        
        for _ in self.p.dummy:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
            
            self.mot(self.p.t_mot_load * s)

            # self.ttl_andor.pulse(self.p.t_andor_expose)

            self.dds.push.off()
            self.switch_d2_2d(0)
            self.switch_d2_3d(0)
            
            self.cmot_d1(self.p.t_d1cmot * s)

            self.gm_tweezer(self.p.t_tweezer_hold * s)
            
            # self.dds.tweezer.off()

            # self.switch_d1_3d(0)
            
            # delay(self.p.t_tweezer_hold)

            # with parallel:
            #     self.mot_reload(self.p.t_andor_expose * s)
            #     self.ttl_andor.pulse(self.p.t_andor_expose)
            
            self.fl_image()
            
            self.release()

            delay(1*s)

        self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")