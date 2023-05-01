from artiq.experiment import *
from artiq.experiment import delay_mu

from kexp.config.dds_id import dds_frame, N_uru
from kexp.control.artiq.DDS import DDS
from kexp.config.expt_params import ExptParams

from jax import AD9910Manager

import numpy as np

dv = -0.1

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
        self.gm_ramp_setup()

        self.dac_ch_3Dmot_current_control = 0

        self.ttl_camera = self.get_device("ttl9")
        self.ttl_magnets = self.get_device("ttl11")

    def gm_ramp_setup(self, t_gm_ramp=dv, ampc_i=dv, ampr_i=dv, power_ramp_factor=dv):

        ### Start defaults ###
        if t_gm_ramp == dv:
            t_gm_ramp = self.params.t_gm_ramp
        if ampc_i == dv:
            ampc_i = self.params.amp_d1_c_gm
        if ampr_i == dv:
            ampr_i = self.params.amp_d1_r_gm
        if power_ramp_factor == dv:
            power_ramp_factor = self.params.power_ramp_factor_gmramp
        ### End defaults ###

        try:
            pic,pir = self.dds.dds_calibration.dds_amplitude_to_power_fraction(
                [ampc_i,ampr_i])
            pfc,pfr = np.array([pic,pir]) / power_ramp_factor
            
            self.dds.set_amplitude_profile(
                self.dds.d1_3d_c,t_gm_ramp,p_i=pic,p_f=pfc)
            self.dds.set_amplitude_profile(
                self.dds.d1_3d_r,t_gm_ramp,p_i=pir,p_f=pfr)
        except:
            # print("Setting up DDS ramp profiles failed. If this is a repo scan, ignore.")
            pass

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

