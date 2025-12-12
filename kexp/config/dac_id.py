import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.zotino import Zotino

from waxx.config.dac_id import dac_frame as dac_frame_waxx
from waxx.control.artiq.DAC_CH import DAC_CH
from kexp.config.expt_params import ExptParams
from kexp.util.db.device_db import device_db

FORBIDDEN_CH = []
N_CH = 32

class dac_frame(dac_frame_waxx):
    def __init__(self, expt_params = ExptParams(), dac_device = Zotino):

        self.setup(expt_params, dac_device, N_CH)
        self.dac_device: Zotino
        self.p: ExptParams

        self.lightsheet_paint_amp = self.assign_dac_ch(0)
        self.vva_lightsheet = self.assign_dac_ch(1,v=9.7)
        self.vva_d1_3d_c = self.assign_dac_ch(2,self.p.v_pd_d1_c_gm)
        self.vva_d1_3d_r = self.assign_dac_ch(3,self.p.v_pd_d1_r_gm)
        self.supply_current_2dmot = self.assign_dac_ch(4,v=2.447)
        self.xshim_current_control = self.assign_dac_ch(5,self.p.v_xshim_current)
        self.yshim_current_control = self.assign_dac_ch(6,self.p.v_yshim_current)
        self.zshim_current_control = self.assign_dac_ch(7,self.p.v_zshim_current)
        self.inner_coil_supply_current = self.assign_dac_ch(8)
        self.outer_coil_supply_current = self.assign_dac_ch(9,max_v=7.)
        self.outer_coil_supply_voltage = self.assign_dac_ch(10)
        self.inner_coil_supply_voltage = self.assign_dac_ch(11)
        self.v_pd_tweezer_pid1 = self.assign_dac_ch(12,v=9.7)
        self.vco_rf = self.assign_dac_ch(13,v=0.)
        
        self.tweezer_paint_amp = self.assign_dac_ch(16)
        self.v_pd_tweezer_pid2 = self.assign_dac_ch(17,v=6.,max_v=10.)
        self.inner_coil_pid = self.assign_dac_ch(18)
        self.outer_coil_pid = self.assign_dac_ch(19)
        self.imaging_pid = self.assign_dac_ch(20, v=1.)
        self.z_shim_mosfet_gate = self.assign_dac_ch(25)
        self.vva_ry_980 = self.assign_dac_ch(26)

        self.vva_ry_405 = self.assign_dac_ch(30)

        self.cleanup()