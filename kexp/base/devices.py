import numpy as np
import time

from artiq.experiment import *
from artiq.experiment import delay_mu, delay
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.coredevice.dma import CoreDMA
from artiq.coredevice.grabber import Grabber
from artiq.coredevice import urukul

from kexp.config.expt_params import ExptParams

from waxx.control.slm.slm import SLM
from waxx.control.artiq.DDS import DDS
from waxx.control.artiq.mirny import Mirny
from waxx.control.artiq.Shuttler_CH import Shuttler_CH
from waxx.control.misc.ssg3021x import SSG3021X
from waxx.control.beat_lock import BeatLockImaging, PolModBeatLock, BeatLockImagingPID
from waxx.control.raman_beams import RamanBeamPair
from waxx.control.cameras.dummy_cam import DummyCamera
from waxx.control.misc.thorlabs_kinesis import WaveplateRotatorPhotodiodePID
from waxx.control.integrator import Integrator

from kexp.config.dds_id import dds_frame, N_uru
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.shuttler_id import shuttler_frame
from kexp.config.sampler_id import sampler_frame
from kexp.config.siglent_id import siglent_frame
from kexp.config.ip import DEVICE_ID_KINESIS_REF_BEAM_WAVEPLATE_ROTATOR
from kexp.config.wavemeter_id import fzw_frame
from kexp.config.data_vault import DataVault, DataContainer

from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.painted_lightsheet import lightsheet
from kexp.control.awg_tweezer import tweezer
from kexp.control.doubled_rf import doubled_rf
from kexp.control.rydberg_lasers import FixedRyDDSBeamPID, FiberEORyDDSBeamPID

from kexp.calibrations.magnets import (slope_i_transducer_per_v_setpoint_supply_outer,
                                       offset_i_transducer_per_v_setpoint_supply_outer,
                                       slope_i_transducer_per_v_setpoint_pid_outer,
                                       offset_i_transducer_per_v_setpoint_pid_outer)

dv = -0.1
d_exptparams = ExptParams()

from waxx.util.artiq.async_print import aprint
from kexp.base.cameras import img_config

class Devices():
    def __init__(self):
        # just to get syntax highlighting
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.params = ExptParams()
        self.raman = RamanBeamPair()
        self.data = DataVault()
        self.p = self.params

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
        # self.grabber = self.get_device("grabber0")
        # self.grabber: Grabber

        # slm
        # self.slm = SLM(expt_params=self.params, core=self.core)

        # sampler channels
        self.sampler = sampler_frame(sampler_device=sampler)

        # dac channels
        self.dac = dac_frame(expt_params=self.params, dac_device=zotino)

        # ttl channels
        self.ttl = ttl_frame()
        self.get_ttl_devices()

        # set up dds_frame
        self.dds = dds_frame(dac_frame_obj=self.dac,
                              core=self.core, expt_params=self.params)
        # self.dds.dds_manager = [DDSManager(self.core)]
        self.get_dds_devices()
        self.dds_list = self.dds.dds_list
        
        self.raman = RamanBeamPair(dds0=self.dds.dds0,
                                    dds1=self.dds.dds1,
                                    dds_sw=self.dds.dds_dummy,
                                    frequency_transition=self.params.frequency_raman_transition,
                                    fraction_power=self.params.fraction_power_raman,
                                    params=self.params)

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
            dds.set_dds(init=True)
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
            dds._store_io_update_delay()
            delay(10.e-6)
            
    @kernel
    def init_all_cpld(self):
        for ddss in self.dds.dds_array:
            ddss[0].cpld_device.init()
            delay(2e-3)
        for dds in self.dds.dds_list:
            dds.dds_device.set_att(0.*dB)

    # def shutdown_sources(self):
    #     from kexp import EthernetRelay
    #     relay = EthernetRelay()
    #     relay.source_off()
