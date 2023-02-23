from artiq.experiment import *
import time

class IdleKernel(EnvExperiment):
    def build(self):
        self.setattr_device("core")

    @kernel
    def run(self):
        start_time = now_mu() + self.core.seconds_to_mu(500*ms)
        while self.core.get_rtio_counter_mu() < start_time:
            pass
        self.core.reset()
        delay(10*s)
        