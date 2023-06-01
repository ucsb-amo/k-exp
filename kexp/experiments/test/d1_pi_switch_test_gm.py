from kexp import Base
from artiq.experiment import *
from artiq.experiment import delay, kernel, parallel

class d1_pi_switch_test_gm(EnvExperiment,Base):
    def build(self):
        Base.__init__(self,setup_camera=False)

    @kernel
    def run(self):
        self.init_kernel()

        delay(100*ms)

        self.gm(t=3*ms, v_pd_d1_c=1.0, v_pd_d1_r=0.5)

        self.release()

        delay(1*s)

        # self.core.break_realtime()
        # self.mot_observe()