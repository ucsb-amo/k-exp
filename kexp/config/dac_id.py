import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.zotino import Zotino
from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.config.expt_params import ExptParams

FORBIDDEN_CH = []

class dac_frame():
    def __init__(self, expt_params = ExptParams(), dac_device = Zotino):

        self.dac_device = dac_device

        self.dac_ch_list = []

        p = expt_params

        self.lightsheet_paint_amp = self.assign_dac_ch(0)
        self.vva_lightsheet = self.assign_dac_ch(1,v=9.7)
        self.vva_d1_3d_c = self.assign_dac_ch(2,p.v_pd_d1_c_gm)
        self.vva_d1_3d_r = self.assign_dac_ch(3,p.v_pd_d1_r_gm)
        self.supply_current_2dmot = self.assign_dac_ch(4,v=2.447)
        self.xshim_current_control = self.assign_dac_ch(5,p.v_xshim_current)
        self.yshim_current_control = self.assign_dac_ch(6,p.v_yshim_current)
        self.zshim_current_control = self.assign_dac_ch(7,p.v_zshim_current)
        self.inner_coil_supply_current = self.assign_dac_ch(8,max_v=5.9)
        self.outer_coil_supply_current = self.assign_dac_ch(9,max_v=7.)
        self.outer_coil_supply_voltage = self.assign_dac_ch(10)
        self.inner_coil_supply_voltage = self.assign_dac_ch(11)
        self.v_pd_tweezer_pid1 = self.assign_dac_ch(12,v=9.7)
        self.vco_rf = self.assign_dac_ch(13,v=0.)
        self.vva_ry_405 = self.assign_dac_ch(14)
        self.vva_ry_980 = self.assign_dac_ch(15)
        self.tweezer_paint_amp = self.assign_dac_ch(16)
        self.v_pd_tweezer_pid2 = self.assign_dac_ch(17,v=6.,max_v=10.)
        self.test_dac = self.assign_dac_ch(30)

        self._write_dac_keys()
        
    def assign_dac_ch(self,ch,v=0.,max_v=9.99) -> DAC_CH:
        if ch in FORBIDDEN_CH:
            raise ValueError(f"DAC channel {ch} is forbidden.")
        this_dac_ch = DAC_CH(ch,self.dac_device, max_v=max_v)
        this_dac_ch.v = v
        self.dac_ch_list.append(this_dac_ch)
        return this_dac_ch
    
    def _write_dac_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],DAC_CH):
                self.__dict__[key].key = key
                self.__dict__[key].set_errmessage()

    def dac_by_ch(self,ch) -> DAC_CH:
        ch_list = [dac.ch for dac in self.dac_ch_list]
        if ch in ch_list:
            ch_idx = ch_list.index(ch)
            return self.dac_ch_list[ch_idx]
        else:
            raise ValueError(f"DAC ch {ch} not assigned in dac_id.")
        
    @kernel
    def set(self,ch,v,load_dac=True):
        self.dac_device.write_dac(channel=ch,voltage=v)
        if load_dac:
            self.dac_device.load()
            
    @kernel
    def load(self):
        self.dac_device.load()