from artiq.experiment import *

class DDS():
   def __init__(self, urukul_idx, ch, freq_MHz=0, att_dB=0):
      self.uidx = urukul_idx
      self.ch = ch
      self.freq_MHz = freq_MHz
      self.att_dB = att_dB
      
   def name(self): 
      return f'urukul{self.uidx}_ch{self.ch}'

class SetDDS(EnvExperiment):

    def build(self):

        self.dds_params = DDS(0,1,100,0)

        self.setattr_device("core")
        self.setattr_device(self.dds_params.name())

        self.dds = self.get_device(self.dds_params.name())

    
    @kernel
    def run(self):

        self.core.reset()

        self.dds.cpld.init()

        self.dds.init()
        self.dds.set(self.dds_params.freq_MHz * MHz, amplitude = 1.)
        self.dds.set_att(self.dds_params.att_dB * dB)

        self.dds.sw.on()