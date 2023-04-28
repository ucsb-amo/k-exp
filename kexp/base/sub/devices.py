from artiq.experiment import *
from artiq.experiment import delay_mu

from kexp.config.dds_id import dds_frame, N_uru
from kexp.control.artiq.DDS import DDS
from kexp.config.expt_params import ExptParams

from jax import AD9910Manager, RAMProfile, RAMType

import numpy as np

class Devices():

    def __init__(self):
        self.params = ExptParams()

    def prepare_devices(self):

        self.core = self.get_device("core")
        self.zotino = self.get_device("zotino0")

        self.dds = dds_frame()
        self.dds.dds_manager = AD9910Manager(self.core)

        self.get_dds_devices()
        self.dds_list = self.dds.dds_list()

        self.dac_ch_3Dmot_current_control = 0

        self.ttl_camera = self.get_device("ttl9")
        self.ttl_magnets = self.get_device("ttl11")

    def get_dds_devices(self):
        for dds in self.dds.dds_list():
            dds.dds_device = self.get_device(dds.name)
            dds.cpld_device = self.get_device(dds.cpld_name)

    @kernel
    def init_kernel(self):
        print(self._ridstr)
        self.core.reset()
        delay_mu(self.params.t_rtio_mu)
        self.zotino.init()
        delay_mu(self.params.t_rtio_mu)
        self.init_all_cpld()
        self.init_all_dds()
        delay(1*ms)
        self.ttl_camera.output()
        self.ttl_magnets.output()
        delay(1*ms)
        self.set_all_dds()
        self.switch_all_dds(0)
        self.core.break_realtime()

    @kernel
    def set_all_dds(self):
        for dds in self.dds_list:
            dds.dds_device.set(frequency = dds.frequency, amplitude = dds.amplitude)
            dds.dds_device.set_att(dds.att_dB * dB)
            delay_mu(self.params.t_rtio_mu)

    @kernel
    def switch_all_dds(self,state):
        for dds in self.dds_list:
            if state == 1:
                dds.on()
            elif state == 0:
                dds.off()
            delay_mu(self.params.t_rtio_mu)

    @kernel
    def init_all_dds(self):
        for dds in self.dds_list:
            dds.dds_device.init()
            delay(1*ms)

    @kernel
    def init_all_cpld(self):
        for dds in self.dds_list:
            dds.cpld_device.init()
            delay(1*ms)

