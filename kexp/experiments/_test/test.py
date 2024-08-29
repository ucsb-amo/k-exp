from artiq.experiment import *
from artiq.experiment import delay

class mot_kill_405(EnvExperiment):

    def prepare(self):
        self.core = self.get_device("core")
        self.ttl = self.get_device("ttl16")
       
    @kernel
    def run(self):
        self.core.reset()
        self.ttl.pulse(1.e-6)