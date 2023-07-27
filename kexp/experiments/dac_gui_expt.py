
from artiq.experiment import *

class SetDACVoltage(EnvExperiment):
    def build(self):
        self.dac_device = self.get_device("zotino0")
        self.core = self.get_device("core")

        self.channel = 26
        self.voltage = 0.22

    @kernel
    def run(self):
        self.core.reset()
        self.dac_device.init()

        dac_value = self.dac_device.voltage_to_mu(self.voltage)

        self.dac_device.write_dac_mu(self.channel, dac_value)

        self.dac_device.load()

        # delay(3*s)

        # self.dac_device.write_dac(self.channel, 0.)

        # self.dac_device.load()
