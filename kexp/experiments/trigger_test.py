from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint
from kexp.config.camera_params import basler_absorp_camera_params

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.t_tof = 1000 * 1.e-6 # mot

        self.p.t_gmramp = 5.e-3

        self.p.dummy = [1]*100

        self.xvarnames = ['dummy']

        # self.params.t_light_only_image_delay = 200.e-3
        # self.params.t_dark_image_delay = 200.e-3

        self.finish_build()

    @kernel
    def run(self):

        count = 0
        
        self.init_kernel()

        delay(3*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for _ in self.p.dummy:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)

            # for _ in range(3):
            #     self.ttl_camera.pulse(10*us)
            #     delay(100*ms)

            self.release()

            ### abs img
            delay(self.p.t_tof * s)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

            aprint(count)
            count += 1

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        # self.ds.save_data(self)

        print("Done!")