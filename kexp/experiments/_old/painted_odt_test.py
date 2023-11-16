from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.dds.lightsheet_paint.frequency = 100 * 1.e3
        self.p.amp_lightsheet_paint = np.linspace(1.0,0.0,100)
        self.p.t_lightsheet_paint_ramp = 5.

        # self.dds.set_amplitude_ramp_profile(self.dds.lightsheet_paint,
        #                                     amp_list=self.p.amp_lightsheet_paint,
        #                                     t_ramp=self.p.t_lightsheet_paint_ramp)

        self.finish_build(cleanup_dds_profiles=False)
        
    @kernel
    def run(self):
        
        self.init_kernel()

        # self.dds.load_profile()
        self.core.break_realtime()

        self.dds.lightsheet.on()
        self.dds.lightsheet_paint.on()
        self.core.break_realtime()

        for a in self.p.amp_lightsheet_paint:
            self.dds.lightsheet_paint.set_dds(amplitude=a)
            delay(100*ms)

        # self.dds.enable_profile()

        # delay(self.p.t_lightsheet_paint_ramp)

        # self.dds.disable_profile()
        self.dds.lightsheet_paint.off()

        delay(3*s)

        self.dds.lightsheet.off()


    def analyze(self):

        # self.camera.Close()

        # self.ds.save_data(self)

        print("Done!")