from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tweezer_test(EnvExperiment, Base):
    def build(self):
        Base.__init__(self)

        self.p = self.params
        
        self.p.test1 = np.linspace(1,2,2)
        self.p.test2 = np.linspace(1,2,2)
        self.p.test3 = np.linspace(1,2,2)
        self.xvarnames = ['test1','test2','test3']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.start_triggered_grab()
        delay(self.p.t_grab_start_wait*s)

        delay(1*s)

        for _ in self.p.test1:
            for _ in self.p.test2:
                for _ in self.p.test3:
                    delay(0.2*s)
                    self.trigger_camera()
                    delay(0.2*s)
                    self.trigger_camera()
                    delay(0.2*s)
                    self.trigger_camera()
                    delay(0.2*s)

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")