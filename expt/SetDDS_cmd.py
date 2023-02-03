from artiq.experiment import *
from DDS import DDS

class SetDDS(EnvExperiment):

    def build(self):

        self.setattr_argument("Urukul_idx", NumberValue(ndecimals=0,step=1))
        self.setattr_argument("Channel", NumberValue(ndecimals=0,step=1))
        self.setattr_argument("freq_MHz", NumberValue(ndecimals=1,step=1))
        self.setattr_argument("att_dB", NumberValue(ndecimals=1,step=1))

        self.dds_params = DDS(self.Urukul_idx,self.Channel,self.freq_MHz,self.att_dB)

        self.setattr_device("core")
        self.setattr_device(self.dds_params.name())

        self.dds = self.get_device(self.dds_params.name())

    
    @kernel
    def run(self):

        self.core.reset()
        self.dds.cpld.init()
        self.dds.init()

        if self.freq_MHz > 0:
            self.dds.set(self.dds_params.freq_MHz * MHz, amplitude = 1.)
            self.dds.set_att(self.dds_params.att_dB * dB)
            self.dds.sw.on()
        else:
            self.dds.sw.off()
            self.dds.power_down()