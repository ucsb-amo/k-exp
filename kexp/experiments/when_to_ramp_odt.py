from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "drop gm before or after ramp?"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = 4
        self.p.t_mot_load = 2.0

        self.p.t_tof = 20.e-6
        self.p.drop_gm_before_ramp_bool = [0,1]

        self.xvarnames = ['drop_gm_before_ramp_bool']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for drop_gm_before_ramp in self.p.drop_gm_before_ramp_bool:

            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp * s)

            if drop_gm_before_ramp:
                self.release()
                self.lightsheet.ramp(t_ramp=self.p.t_lightsheet_rampup)
            else:
                self.lightsheet.ramp(t_ramp=self.p.t_lightsheet_rampup)
                self.release()
            
            delay(25.e-3)
            self.lightsheet.off()

            delay(self.p.t_tof * s)
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")