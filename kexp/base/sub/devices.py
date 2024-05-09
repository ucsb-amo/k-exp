from artiq.experiment import *
from artiq.experiment import delay_mu, delay
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.coredevice.dma import CoreDMA

from kexp.config.dds_id import dds_frame, N_uru
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.control.artiq.mirny import Mirny
from kexp.config.expt_params import ExptParams

# from jax import AD9910Manager
from kexp.control.cameras.dummy_cam import DummyCamera

from kexp.control.misc.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.misc.painted_lightsheet import lightsheet
from kexp.control.misc.awg_tweezer import tweezer
from kexp.control.misc.doubled_rf import doubled_rf

import numpy as np

dv = -0.1
d_exptparams = ExptParams()

class Devices():

    def prepare_devices(self,expt_params:ExptParams=d_exptparams):
        # for syntax highlighting

        self.params = expt_params
        self.params.compute_derived()

        self.core = Core
        zotino = Zotino
        self.core_dma = CoreDMA

        # get em
        self.core = self.get_device("core")
        self.core_dma = self.get_device("core_dma")
        zotino = self.get_device("zotino0")

        # dac channels
        self.dac = dac_frame(dac_device=zotino)

        # ttl channels
        self.ttl = ttl_frame()
        self.get_ttl_devices()

        # set up dds_frame
        self.dds = dds_frame(dac_frame_obj=self.dac, core=self.core, expt_params=self.params)
        # self.dds.dds_manager = [DDSManager(self.core)]
        self.get_dds_devices()
        self.dds_list = self.dds.dds_list

        self.rf = doubled_rf(dds_ch=self.dds.antenna_rf, expt_params=self.params)

        # magnet coils
        self.inner_coil = hbridge_magnet(max_current=170.,
                                         max_voltage=80.,
                                         v_control_dac=self.dac.inner_coil_supply_voltage,
                                         i_control_dac=self.dac.inner_coil_supply_current,
                                         igbt_ttl=self.ttl.inner_coil_igbt,
                                         contactor_ttl=self.ttl.inner_coil_contactor,
                                         hbridge_ttl=self.ttl.hbridge_helmholtz,
                                         expt_params=self.params)
                                      
        self.outer_coil = igbt_magnet(max_current=500.,
                                      max_voltage=80.,
                                      v_control_dac=self.dac.outer_coil_supply_voltage,
                                      i_control_dac=self.dac.outer_coil_supply_current,
                                      igbt_ttl=self.ttl.outer_coil_igbt,
                                      contactor_ttl=self.ttl.outer_coil_contactor,
                                      expt_params=self.params)
        
        # painted ligthsheet
        self.lightsheet = lightsheet(vva_dac=self.dac.vva_lightsheet,
                                     paint_amp_dac=self.dac.lightsheet_mod_amp,
                                     sw_ttl=self.ttl.lightsheet_sw,
                                     expt_params=self.params)
        
        self.tweezer = tweezer(self.dac.vva_tweezer,
                               sw_ttl=self.ttl.awg,
                               awg_trg_ttl = self.ttl.awg_trigger,
                               expt_params=self.params)

        # camera placeholder
        self.camera = DummyCamera()

    def get_ttl_devices(self):
        for ttl in self.ttl.ttl_list:
            ttl.ttl_device = self.get_device(ttl.name)

    def get_dds_devices(self):
        for dds in self.dds.dds_list:
            dds.dds_device = self.get_device(dds.name)
            dds.cpld_device = self.get_device(dds.cpld_name)

    @kernel
    def set_all_dds(self):
        for dds in self.dds.dds_list:
            dds.set_dds(set_stored=True)
            dds.dds_device.set_att(0. * dB)
            delay(self.params.t_rtio)

    @kernel
    def switch_all_dds(self,state):
        for dds in self.dds.dds_list:
            if state == 1:
                dds.on()
            elif state == 0:
                dds.off()
            delay(self.params.t_rtio)

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