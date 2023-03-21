from artiq.experiment import *
from artiq.experiment import delay_mu
from kexp.util.db.device_db import device_db
from kexp.config.expt_params import ExptParams
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

      self._t_rtio_mu = ExptParams().t_rtio_mu

   def detuning_to_frequency(self,linewidths_detuned,single_pass=False):
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
         The corresponding AOM frequency setting in MHz.
      '''
      f_shift_to_resonance_MHz = 461.7 / 2 # half the crossover detuning. Value from T.G. Tiecke.
      linewidth_MHz = 6
      detuning_MHz = linewidths_detuned * linewidth_MHz
      freq = np.abs( ( self.aom_order * f_shift_to_resonance_MHz + detuning_MHz ) / 2 )
      if single_pass:
         freq = freq * 2
      return freq
      
   def name(self) -> TStr:
      return f'urukul{self.urukul_idx}_ch{self.ch}'

   @kernel
   def set_dds(self, freq_MHz = -0.1, att_dB = -0.1):
      '''Set the dds device. If freq_MHz = 0, turn it off'''

      if freq_MHz < 0.:
         freq_MHz = self.freq_MHz
      else:
         self.freq_MHz = freq_MHz

      if att_dB < 0.:
         att_dB = self.att_dB
      else:
         self.att_dB = att_dB

      self.init_dds()
      if self.freq_MHz != 0.:
         self.dds_device.set(self.freq_MHz * MHz, amplitude = 1.)
         self.dds_device.set_att(self.att_dB * dB)
      else:
         self.dds_device.sw.off()

   @kernel
   def off(self):
      self.init_dds()
      self.dds_device.sw.off()

   @kernel
   def on(self):
      self.init_dds()
      self.dds_device.sw.on()

   @kernel
   def init_dds(self):
      delay_mu(-self._t_rtio_mu)
      self.dds_device.init()
      delay_mu(self._t_rtio_mu)

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