import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.zotino import Zotino
from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.DDS import DDS

FORBIDDEN_CH = [4]

class dac_frame():
    def __init__(self,dac_device=Zotino):

        self.dac_device = dac_device

        self.dac_ch_list = []

        self.mot_current_control = self.assign_dac_ch(0)
        self.vva_d1_3d_r = self.assign_dac_ch(1)
        self.vva_d1_3d_c = self.assign_dac_ch(2)
        self.vva_tweezer = self.assign_dac_ch(3)
        self.vva_lightsheet = self.assign_dac_ch(5)
        self.zshim_current_control = self.assign_dac_ch(6)

        self._write_dac_keys()
        
    def assign_dac_ch(self,ch) -> DAC_CH:
        if ch in FORBIDDEN_CH:
            raise ValueError(f"DAC channel {ch} is forbidden.")
        this_dac_ch = DAC_CH(ch,self.dac_device)
        self.dac_ch_list.append(this_dac_ch)
        return this_dac_ch
    
    def _write_dac_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],DAC_CH):
                self.__dict__[key].key = key

    def write_dac(self,ch,v,load_dac=True):
        self.dac_device.write_dac(channel=ch,voltage=v)
        if load_dac:
            self.dac_device.load()

    def dac_by_ch(self,ch):
        ch_list = [dac.ch for dac in self.dac_ch_list]
        ch_idx = ch_list.index(ch)
        if ch_idx:
            return ch_list[ch_idx]
        else:
            raise ValueError(f"DAC ch {ch} not assigned in dac_id.")