from artiq.experiment import *
class TestTTL(EnvExperiment):
    def build(self):
        self.core = self.get_device("core")
        self.ttl = self.get_device("ttl8")
        self.t = 1.e-6
    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()
        for _ in range(5):
            self.ttl.on()
            delay(self.t * s)
            self.ttl.off()
            delay(self.t * s)