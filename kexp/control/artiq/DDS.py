from artiq.experiment import *
from kexp.util.db.device_db import device_db
from kexp.config.dds_id import dds_id

class DDS():
   def __init__(self, urukul_idx, ch, freq_MHz=0., att_dB=0.):
      self.urukul_idx = urukul_idx
      self.ch = ch
      self.freq_MHz = freq_MHz
      self.att_dB = att_dB
      self.aom_order = []
      self.varname = []
      self.dds_device = []
      self.cpld_name = []
      self.bus_channel = []
      self.ftw_per_hz = 0
      self.read_db(device_db)
      self.get_id()

   def set_detuning(self,detuning_linewidths):
      '''
      Sets the stored DDS frequency value based on a detuning given in units of
      the D1, D2 linewidths Gamma = 2 * pi * 6 MHz.

      Note: only the value stored in software is updated. Use set_dds after this
      to update the output.
      '''
      f_shift_to_resonance_MHz = 461.7 / 2 # half the crossover detuning. Value from T.G. Tiecke.
      linewidth_MHz = 6
      detuning_MHz = detuning_linewidths * linewidth_MHz
      self.freq_MHz = ( self.aom_order * f_shift_to_resonance_MHz + detuning_MHz ) / 2
      
   def get_id(self):
      varname, aom_order = dds_id(self.urukul_idx,self.ch)
      self.varname = varname
      self.aom_order = aom_order
      
   def name(self) -> TStr:
      return f'urukul{self.urukul_idx}_ch{self.ch}'

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

   @kernel
   def off(self):
      self.dds_device.sw.off()

   @kernel
   def on(self):
      self.dds_device.sw.on()

   def read_db(self,ddb):
      '''read out info from ddb. ftw_per_hz comes from artiq.frontend.moninj, line 206-207'''
      v = device_db[self.name()]
      self.cpld_name = v["arguments"]["cpld_device"]
      spi_dev = ddb[self.cpld_name]["arguments"]["spi_device"]
      self.bus_channel = ddb[spi_dev]["arguments"]["channel"]
      pll = v["arguments"]["pll_n"]
      refclk = ddb[self.cpld_name]["arguments"]["refclk"]

      sysclk = refclk / 4 * pll
      max_freq = 1 << 32

      self.ftw_per_hz = 1 / sysclk * max_freq

   def ftw_to_freq(self,ftw):
      return ftw / self.ftw_per_hz