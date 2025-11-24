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
from waxx.control.cameras.dummy_cam import DummyCamera

from kexp.config.dds_id import dds_frame, N_uru
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.shuttler_id import shuttler_frame
from kexp.config.sampler_id import sampler_frame

from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.painted_lightsheet import lightsheet
from kexp.control.awg_tweezer import tweezer
from kexp.control.doubled_rf import doubled_rf
from kexp.control.raman_beams import RamanBeamPair

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
        # self.grabber = self.get_device("grabber0")
        # self.grabber: Grabber

        # slm
        self.slm = SLM(expt_params=self.params, core=self.core)

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
                             shuttler_frame_obj=self.shuttler,
                              core=self.core, expt_params=self.params)
        # self.dds.dds_manager = [DDSManager(self.core)]
        self.get_dds_devices()
        self.dds_list = self.dds.dds_list

        self.rf = doubled_rf(dds_ch=self.dds.antenna_rf, expt_params=self.params)

        # magnet coils
        self.inner_coil = hbridge_magnet(max_current=170.,
                                        max_voltage=80.,
                                        v_control_dac=self.dac.inner_coil_supply_voltage,
                                        i_control_dac=self.dac.inner_coil_supply_current,
                                        pid_dac=self.dac.inner_coil_pid,
                                        pid_ttl=self.ttl.inner_coil_pid_ttl,
                                        igbt_ttl=self.ttl.inner_coil_igbt,
                                        #  discharge_igbt_ttl=self.ttl.coil_discharge_igbt,
                                        discharge_igbt_ttl=self.ttl.test_trig,
                                        hbridge_ttl=self.ttl.hbridge_helmholtz,
                                        expt_params=self.params,
                                        slope_current_per_vdac_supply=17.)
                                      
        self.outer_coil = igbt_magnet(max_current=500.,
                                        max_voltage=80.,
                                        v_control_dac=self.dac.outer_coil_supply_voltage,
                                        i_control_dac=self.dac.outer_coil_supply_current,
                                        pid_dac=self.dac.outer_coil_pid,
                                        pid_ttl=self.ttl.outer_coil_pid_ttl,
                                        igbt_ttl=self.ttl.outer_coil_igbt,
                                        #   discharge_igbt_ttl=self.ttl.coil_discharge_igbt,
                                        discharge_igbt_ttl=self.ttl.test_trig,
                                        expt_params=self.params,
                                        slope_current_per_vdac_supply=slope_i_transducer_per_v_setpoint_supply_outer,
                                        offset_current_per_vdac_supply=offset_i_transducer_per_v_setpoint_supply_outer,
                                        slope_current_per_vdac_pid=slope_i_transducer_per_v_setpoint_pid_outer,
                                        offset_current_per_vdac_pid=offset_i_transducer_per_v_setpoint_pid_outer)
        
        # painted ligthsheet
        self.lightsheet = lightsheet(pid_dac=self.dac.vva_lightsheet,
                                     paint_amp_dac=self.dac.lightsheet_paint_amp,
                                     alignment_shim_dac=self.dac.zshim_current_control,
                                     sw_ttl=self.ttl.lightsheet_sw,
                                     pid_int_hold_zero_ttl = self.ttl.lightsheet_pid_int_hold_zero,
                                     expt_params=self.params)
        
        self.tweezer = tweezer(ao1_dds=self.dds.tweezer_pid_1,
                               pid1_dac=self.dac.v_pd_tweezer_pid1,
                               ao2_dds=self.dds.tweezer_pid_2,
                               pid2_dac=self.dac.v_pd_tweezer_pid2,
                               sw_ttl=self.ttl.aod_rf_sw,
                               awg_trg_ttl = self.ttl.awg_trigger,
                               pid1_int_hold_zero_ttl = self.ttl.tweezer_pid1_int_hold_zero,
                               pid2_enable_ttl=self.ttl.tweezer_pid2_enable,
                               painting_dac = self.dac.tweezer_paint_amp,
                               expt_params = self.params,
                               core=self.core)
        
        self.raman = RamanBeamPair(dds0=self.dds.raman_150_plus,
                                    dds1=self.dds.raman_80_plus,
                                    frequency_transition=self.params.frequency_raman_transition,
                                    fraction_power=self.params.fraction_power_raman,
                                    params=self.params)
        
        # self.raman_lf_hf = RamanBeamPair(dds0=self.dds.raman_150_minus,
        #                                 dds1=self.dds.raman_80_plus,
        #                                 frequency_transition=self.params.frequency_raman_transition,
        #                                 fraction_power=self.params.fraction_power_raman,
        #                                 params=self.params)
        
        self.raman_nf = RamanBeamPair(dds0=self.dds.raman_150_minus,
                                    dds1=self.dds.raman_80_plus,
                                    frequency_transition=self.params.frequency_raman_transition,
                                    fraction_power=self.params.fraction_power_raman,
                                    params=self.params)
        
        # self.ry_980_eo = SSG3021X()

        # camera placeholder
        self.camera = DummyCamera()

    def configure_imaging_system(self, imaging_configuration):
        N = 8
        beatref_sign = -1
        f_min_beat = 250.e6
        
        if imaging_configuration == img_config.PID:
            self.imaging = BeatLockImagingPID(dds_sw=self.dds.imaging_x_switch,
                                              dds_beatref=self.dds.beatlock_ref,
                                              dds_pid=self.dds.imaging,
                                              pid_int_clear_ttl=self.ttl.imaging_pid_int_clear_hold,
                                              pid_override_ttl=self.ttl.imaging_pid_manual_override,
                                              N_beatref_mult=N,
                                              beatref_sign=beatref_sign,
                                              frequency_minimum_beat=f_min_beat,
                                              expt_params=self.params)
        elif imaging_configuration == img_config.SWITCH:
            self.imaging = BeatLockImaging(dds_sw=self.dds.imaging,
                                           dds_beatref=self.dds.beatlock_ref,
                                           pid_override_ttl=self.ttl.imaging_pid_manual_override,
                                           N_beatref_mult=N,
                                           beatref_sign=beatref_sign,
                                           frequency_minimum_beat=f_min_beat,
                                           expt_params=self.params)
        # elif imaging_configuration == img_config.POLMOD:
        #     self.imaging = PolModBeatLock(dds_sw=self.dds.imaging,
        #                             dds_polmod_v=self.dds.polmod_v,
        #                             dds_polmod_h=self.dds.polmod_h,
        #                             dds_beatref=self.dds.beatlock_ref,
        #                             pid_override_ttl=self.ttl.imaging_pid_manual_override,
        #                             N_beatref_mult=N, beatref_sign=beatref_sign,
        #                             frequency_minimum_beat=f_min_beat,
        #                             expt_params=self.params)

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

    def shutdown_sources(self):
        from kexp import EthernetRelay
        relay = EthernetRelay()
        relay.source_off()
