from artiq.experiment import *
from kexp import Base

class setdds(EnvExperiment,Base):
    def build(self):
        Base.__init__(self)

        self.mydds = self.dds.d1_3d_r

        self.f = self.mydds.freq_MHz * MHz

        # self.att = self.mydds.att_dB
        # self.a = 1.0

        self.a = 0.092
        self.att = 0.0

    @kernel
    def run(self):
        self.init_kernel()
        self.mydds.dds_device.set_att(self.att)
        self.mydds.dds_device.set(frequency=self.f, amplitude = self.a)
        self.mydds.on()