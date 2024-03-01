from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True)

        print(self.ttl.camera.ch)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.0

        self.xvar('t_tof',np.linspace(1000,12000,3)*1.e-6)

        self.finish_build()

    @kernel
    def scan_kernel(self):
        # self.mot(self.p.t_mot_load * s)
        # self.dds.push.off()
        # self.cmot_d1(self.p.t_d1cmot * s)
        # self.set_shims(v_zshim_current=.84, v_yshim_current=self.p.v_yshim_current, v_xshim_current=self.p.v_xshim_current)
        # self.gm(self.p.t_gm * s)
        # self.release()

        delay(1*s)
        
        self.abs_image()

        delay(1*s)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        # self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        self.scan()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")