from artiq.experiment import *
from artiq.experiment import delay_mu, delay, parallel
from artiq.language.core import now_mu, at_mu
from kexp.util.db.device_db import device_db
import numpy as np

from artiq.coredevice import adf5356

from kexp.util.artiq.async_print import aprint

DAC_CH_DEFAULT = -1

class DDS():
    def __init__(self, mirny_idx, ch, frequency=0., power_level=3):
      
        self.mirny_idx = mirny_idx
        self.ch = ch
        self.frequency = frequency
        self.power_level = power_level
        self.key = ""

        self.mirny_device = adf5356.ADF5356
        self.name = f'mirny{self.mirny_idx}_ch{self.ch}'
        self.cpld_name = f'mirny{self.mirny_idx}_cpld'

    def get_devices(self,expt):
        self.mirny_device = expt.get_device(self.name)
        self.cpld_device = expt.get_device(self.cpld_name)

    @kernel
    def off(self):
        self.mirny_device.sw.off()

    @kernel
    def on(self):
        self.mirny_device.sw.on()

    @kernel
    def init(self):
        self.cpld_device.init()
        delay(1*ms)
        self.mirny_device.init()
        delay(1*ms)
        self.mirny_device.set_output_power_mu(self.power_level)