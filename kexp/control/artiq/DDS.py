from artiq.experiment import *
from artiq.experiment import delay_mu, delay, parallel
from artiq.language.core import now_mu, at_mu
from kexp.util.db.device_db import device_db
import numpy as np

from artiq.coredevice import ad9910
from artiq.coredevice.urukul import CPLD

from kexp.util.artiq.async_print import aprint
from kexp.config.dds_calibration import DDS_Calibration as ddscal

class DDS():

   def __init__(self, urukul_idx, ch, frequency=0., amplitude=0., att_dB=0.):
      self.urukul_idx = urukul_idx
      self.ch = ch
      self.frequency = frequency
      self.amplitude = amplitude
      self.att_dB = att_dB
      self.aom_order = []
      self.transition = []
      self.dds_device = ad9910.AD9910
      self.name = f'urukul{self.urukul_idx}_ch{self.ch}'
      self.cpld_name = []
      self.cpld_device = CPLD
      self.bus_channel = []
      self.ftw_per_hz = 0
      self.read_db(device_db)

      self.dds_calibration = ddscal()

      self._t_att_xfer_mu = np.int64(1592) # see https://docs.google.com/document/d/1V6nzPmvfU4wNXW1t9-mRdsaplHDKBebknPJM_UCvvwk/edit#heading=h.10qxjvv6p35q
      self._t_set_xfer_mu = np.int64(1248) # see https://docs.google.com/document/d/1V6nzPmvfU4wNXW1t9-mRdsaplHDKBebknPJM_UCvvwk/edit#heading=h.e1ucbs8kjf4z
      self._t_ref_period_mu = np.int64(8) # one clock cycle, 125 MHz --> T = 8 ns (mu)

      self._t_set_delay_mu = self._t_set_xfer_mu + self._t_ref_period_mu + 1
      self._t_att_delay_mu = self._t_att_xfer_mu + self._t_ref_period_mu + 1

   @portable(flags={"fast-math"})
   def detuning_to_frequency(self,linewidths_detuned,single_pass=False) -> TFloat:
      '''
      Returns the DDS frequency value in MHz corresponding to detuning =
      linewidths_detuned * Gamma from the resonant D1, D2 transitions. Gamma = 2
      * pi * 6 MHz.

      D1 AOMs give detuning relative to |g> -> |F'=2>.
      D2 AOMs give detuning relative to |g> -> unresolved D2 peak.

      Parameters
      ----------
      linewidths_detuned: float
         Detuning in units of linewidth Gamma = 2 * pi * 6 MHz.

      Returns
      -------
      float
         The corresponding AOM frequency setting in Hz.
      '''
      linewidths_detuned=float(linewidths_detuned)

      f_shift_to_resonance_MHz = 461.7 / 2 # half the crossover detuning. Value from T.G. Tiecke.
      
      # f_D1_shift_from_F1_to_F2 = 55.5

      linewidth_MHz = 6
      detuning_MHz = linewidths_detuned * linewidth_MHz
      freq = ( self.aom_order * f_shift_to_resonance_MHz + detuning_MHz ) / 2

      # if self.transition == 'D1':
      #    freq += f_D1_shift_from_F1_to_F2 / 2
      # if self.transition == 'D2':
      #    pass

      if freq < 0.:
         freq = -freq

      if single_pass:
         freq = freq * 2

      return freq * 1.e6
   
   @kernel(flags={"fast-math"})
   def set_dds_gamma(self, delta=-1000., amplitude=-0.1, att_dB=-0.1):
      '''
      Sets the DDS frequency and attenuation. Uses delta (detuning) in units of
      gamma, the linewidth of the D1 and D2 transition (Gamma = 2 * pi * 6 MHz).

      Parameters:
      -----------
      delta: float
         Detuning in units of linewidth Gamma = 2 * pi * 6 MHz. (default: use
         stored self.frequency)

      att_dB: float
         The attenuation in units of dB. (default: stored self.att_dB)
      '''
      delta = float(delta)

      if delta == -1000.:
         frequency = -0.1
      else:
         frequency = self.detuning_to_frequency(linewidths_detuned=delta)
      
      self.set_dds(frequency=frequency, amplitude=amplitude, att_dB=att_dB)

   @kernel(flags={"fast-math"})
   def set_dds(self, frequency = -0.1, amplitude = -0.1, att_dB = -0.1, set_stored = False):
      '''Set the dds device. If frequency = 0, turn it off'''

      if set_stored:
         if frequency < 0.:
            frequency = self.frequency
         if amplitude < 0.:
            amplitude = self.amplitude
         if att_dB < 0.:
            att_dB = self.att_dB

      _set_freq = frequency > 0.
      _set_amp = amplitude > 0.
      _set_freq_or_amp = _set_freq or _set_amp
      _set_att = att_dB > 0.
      _set_both = (_set_freq_or_amp and _set_att)
      
      # tnow = now_mu()

      if _set_att:
         self.att_dB = att_dB
         # delay_mu(-self._t_att_xfer_mu - self._t_ref_period_mu)

      # if _set_freq_or_amp:
         # dt = now_mu() - (now_mu() & ~7)
         # delay_mu(-(dt + self._t_set_xfer_mu))

      if _set_freq:
         self.frequency = frequency
      elif frequency == 0.:
         self.dds_device.sw.off()

      if _set_amp:
         self.amplitude = amplitude
      elif amplitude == 0.:
         self.amplitude = 0.
         self.dds_device.set(amplitude=self.amplitude)
         self.dds_device.sw.off()
      
      if _set_both:
         self.dds_device.set(frequency=self.frequency,amplitude=self.amplitude)
         self.dds_device.set_att(self.att_dB)
      elif _set_att:
         self.dds_device.set_att(self.att_dB)
      elif _set_freq_or_amp:
         self.dds_device.set(frequency=self.frequency,amplitude=self.amplitude)

      # if _set_freq_or_amp:
      #    delay_mu(-self._t_ref_period_mu + dt)

   def get_devices(self,expt):
      self.dds_device = expt.get_device(self.name)
      self.cpld_device = expt.get_device(self.cpld_name)

   @kernel
   def off(self):
      self.dds_device.sw.off()

   @kernel
   def on(self):
      self.dds_device.sw.on()

   def read_db(self,ddb):
      '''read out info from ddb. ftw_per_hz comes from artiq.frontend.moninj, line 206-207'''
      v = device_db[self.name]
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
   
   