from artiq.experiment import delay, kernel
from artiq.coredevice.ttl import TTLOut
import artiq.experiment

class TTL():
    def __init__(self,ch):
        self.ch = ch
        self.ttl_device = TTLOut
        self.name = f'ttl{self.ch}'
        self.key = ""

    @kernel
    def get_device(self,expt:artiq.experiment.EnvExperiment):
        expt.get_device(self.name)

    @kernel
    def on(self):
        self.ttl_device.on()

    @kernel
    def off(self):
        self.ttl_device.off()

    @kernel
    def pulse(self,t):
        self.ttl_device.on()
        delay(t)
        self.ttl_device.off()
