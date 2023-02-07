from artiq.experiment import *

class DDS():
   def __init__(self, urukul_idx, ch, freq_MHz=0., att_dB=0.):
      self.uidx = urukul_idx
      self.ch = ch
      self.freq_MHz = freq_MHz
      self.att_dB = att_dB
      self.dds_device = []
      
   def name(self) -> TStr:
      return f'urukul{self.uidx}_ch{self.ch}'

   @kernel
   def init_dds(self):
      self.dds_device.cpld.init()
      self.dds_device.init()

   @kernel
   def set_dds(self):
      '''Set the dds device. If freq_MHz = 0, turn it off'''

      if self.freq_MHz != 0.:
         self.dds_device.set(self.freq_MHz * MHz, amplitude = 1.)
         self.dds_device.set_att(self.att_dB * dB)
         self.dds_device.sw.on()
      else:
         self.dds_device.sw.off()
         self.dds_device.power_down()