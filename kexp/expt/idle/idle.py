from artiq.experiment import *

class IdleKernel(EnvExperiment):
    def build(self):
        self.setattr_device("core")

    @kernel
    def run(self):
        self.core.reset()
        start_time = now_mu() + self.core.seconds_to_mu(20*s)
        while self.core.get_rtio_counter_mu() < start_time:
            pass
        self.core.reset()