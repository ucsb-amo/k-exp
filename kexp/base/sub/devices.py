from artiq.experiment import *
from artiq.experiment import delay_mu
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.coredevice.dma import CoreDMA

from kexp.config.dds_id import dds_frame, N_uru, DDSManager
from kexp.config.ttl_id import ttl_frame
from kexp.control.artiq import TTL
from kexp.config.expt_params import ExptParams

from jax import AD9910Manager
from kexp.control.cameras.dummy_cam import DummyCamera

import numpy as np

dv = -0.1

class Devices():

    def __init__(self):
        self.params = ExptParams()

    def prepare_devices(self):
        # for syntax highlighting
        self.core = Core
        self.zotino = Zotino
        self.core_dma = CoreDMA

        # get em
        self.core = self.get_device("core")
        self.core_dma = self.get_device("core_dma")
        self.zotino = self.get_device("zotino0")

        # set up dds_frame
        self.dds = dds_frame(dac_device=self.zotino, core=self.core)
        self.dds.dds_manager = [DDSManager(self.core)]
        self.get_dds_devices()
        self.dds_list = self.dds.dds_list

        # dac channels
        self.dac_ch_3Dmot_current_control = 0
        self.dac_ch_zshim_current_control = 6

        # ttl channels
        self.ttl = ttl_frame()
        self.get_ttl_devices()

        # camera placeholder
        self.camera = DummyCamera()

    def get_ttl_devices(self):
        for ttl in self.ttl.ttl_list:
            self.get_device(ttl.name)

    def get_dds_devices(self):
        for dds in self.dds.dds_list:
            dds.dds_device = self.get_device(dds.name)
            dds.cpld_device = self.get_device(dds.cpld_name)

    @kernel
    def set_all_dds(self):
        for dds in self.dds.dds_list:
            dds.set_dds(set_stored=True)
            dds.dds_device.set_att(0. * dB)
            delay_mu(self.params.t_rtio_mu)

    @kernel
    def switch_all_dds(self,state):
        for dds in self.dds.dds_list:
            if state == 1:
                dds.on()
            elif state == 0:
                dds.off()
            delay_mu(self.params.t_rtio_mu)

    @kernel
    def init_all_dds(self):
        for dds in self.dds.dds_list:
            dds.dds_device.init()
            delay(1*ms)

    @kernel
    def init_all_cpld(self):
        for dds in self.dds.dds_list:
            dds.cpld_device.init()
            delay(1*ms)

        ###