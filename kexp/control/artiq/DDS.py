from artiq.experiment import *
from kexp.util.db.device_db import device_db
import numpy as np

class DDS():
   def __init__(self, urukul_idx, ch, freq_MHz=0., att_dB=0.):
      self.urukul_idx = urukul_idx
      self.ch = ch
      self.freq_MHz = freq_MHz
      self.att_dB = att_dB
      self.aom_order = []
      self.dds_device = []
      self.cpld_name = []
      self.bus_channel = []
      self.ftw_per_hz = 0
      self.read_db(device_db)

   def detuning_to_frequency(self,linewidths_detuned):
      '''
      Returns the DDS frequency value in MHz corresponding to detuning =
      linewidths_detuned * Gamma from the resonant D1, D2 transitions. Gamma = 2
      * pi * 6 MHz.

      D1 AOMs give detuning relative to |g> -> |F=2>.
      D2 AOMs give detuning relative to |g> -> unresolved D2 peak (fine
      structure center frequency).

      Parameters
      ----------
      linewidths_detuned: float
         Detuning in units of linewidth Gamma = 2 * pi * 6 MHz.

      Returns
      -------
      float
         The AOM frequency setting in MHz.
      '''
      f_shift_to_resonance_MHz = 461.7 / 2 # half the crossover detuning. Value from T.G. Tiecke.
      linewidth_MHz = 6
      detuning_MHz = linewidths_detuned * linewidth_MHz
      return np.abs( ( self.aom_order * f_shift_to_resonance_MHz + detuning_MHz ) / 2 )
      
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