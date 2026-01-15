import numpy as np

from artiq.experiment import *
from artiq.experiment import delay_mu, delay
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.coredevice.dma import CoreDMA
from artiq.coredevice.grabber import Grabber

from kexp.config.expt_params import ExptParams

from waxx.control.slm.slm import SLM
from waxx.control.artiq.DDS import DDS
from waxx.control.artiq.mirny import Mirny
from waxx.control.artiq.Shuttler_CH import Shuttler_CH
from waxx.control.misc.ssg3021x import SSG3021X
from waxx.control.beat_lock import BeatLockImaging, PolModBeatLock, BeatLockImagingPID
from waxx.control.raman_beams import RamanBeamPair
from waxx.control.cameras.dummy_cam import DummyCamera

from kexp.config.dds_id import dds_frame, N_uru
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.shuttler_id import shuttler_frame
from kexp.config.sampler_id import sampler_frame
from kexp.config.siglent_id import siglent_frame

from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.painted_lightsheet import lightsheet
from kexp.control.awg_tweezer import tweezer
from kexp.control.doubled_rf import doubled_rf
from kexp.control.rydberg_lasers import RydbergLasers, CavityAOControlledRyDDSBeam

from kexp.calibrations.magnets import (slope_i_transducer_per_v_setpoint_supply_outer,
                                       offset_i_transducer_per_v_setpoint_supply_outer,
                                       slope_i_transducer_per_v_setpoint_pid_outer,
                                       offset_i_transducer_per_v_setpoint_pid_outer)

dv = -0.1
d_exptparams = ExptParams()

from waxx.util.artiq.async_print import aprint
from kexp.base.cameras import img_config

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
        sampler = self.get_device("sampler0")

        # sampler channels
        self.sampler = sampler_frame(sampler_device=sampler)

        # dac channels
        self.dac = dac_frame(expt_params=self.params, dac_device=zotino)

        self.shuttler = shuttler_frame()
        self.get_shuttler_devices()

        # ttl channels
        self.ttl = ttl_frame()
        self.get_ttl_devices()

        # set up dds_frame
        self.dds = dds_frame(dac_frame_obj=self.dac,
                            core=self.core, expt_params=self.params)
        self.get_dds_devices()
        self.dds_list = self.dds.dds_list

        # camera placeholder
        self.camera = DummyCamera()

    def get_ttl_devices(self):
        for ttl in self.ttl.ttl_list:
            ttl.ttl_device = self.get_device(ttl.name)

    def get_dds_devices(self):
        for dds in self.dds.dds_list:
            dds.dds_device = self.get_device(dds.name)
            dds.cpld_device = self.get_device(dds.cpld_name)

    def get_shuttler_devices(self):
        self.shuttler._config = self.get_device("shuttler0_config")
        self.shuttler._relay = self.get_device("shuttler0_relay")
        self.shuttler._trigger = self.get_device("shuttler0_trigger")

        for shuttler_ch in self.shuttler.shuttler_list:
            shuttler_ch._dc = self.get_device(shuttler_ch._dc_name)
            shuttler_ch._dds = self.get_device(shuttler_ch._dds_name)
            shuttler_ch._relay = self.shuttler._relay
            shuttler_ch._trigger = self.shuttler._trigger

    @kernel
    def set_all_dds(self):
        for dds in self.dds.dds_list:
            dds.set_dds(init=True)
            dds.dds_device.set_att(0. * dB)
            delay(5.e-6)

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
            delay(10*us)

    @kernel
    def init_all_cpld(self):
        for ddss in self.dds.dds_array:
            ddss[0].cpld_device.init()
            delay(10*us)
