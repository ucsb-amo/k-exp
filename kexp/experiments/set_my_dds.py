from artiq.experiment import *

class setdds(EnvExperiment):
    def build(self):
        self.core = self.get_device("core")
        self.dds = self.get_device("urukul2_ch2")
        self.cpld = self.get_device("urukul2_cpld")

        # set amp here
        self.amp = 0.33

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()
        
        self.cpld.init()
        self.dds.init()
        delay(1*ms)

        self.dds.set(frequency=100.e6,amplitude=self.amp)
        self.dds.sw.on()