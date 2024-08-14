from artiq.experiment import *

class test_6(EnvExperiment):

    def prepare(self):
        self.core = self.get_device("core")
        self.dac = self.get_device("zotino0")

    @kernel
    def run(self):
        
        v = 4.

        self.core.reset()
        self.dac.write_dac(28,v)
        self.dac.load()