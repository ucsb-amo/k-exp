import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.zotino import Zotino
from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.config.expt_params import ExptParams

IGNORE_CH = []
N_ch = 32
CH_IDX = list( np.array(range(N_ch))[ [idx not in IGNORE_CH for idx in range(N_ch)] ] )

class dac_frame():
    def __init__(self, expt_params = ExptParams(), dac_device = Zotino):

        self.dac_device = dac_device

        self.dac_ch_list = [DAC_CH(0) for _ in range(N_ch)]
        
        p = expt_params

        self.test = self.assign_dac_ch(0,0.)

        self._write_dac_keys()
        self._fill_dac_list()
        
    def assign_dac_ch(self,ch,v=0.,max_v=9.99) -> DAC_CH:
        if ch in IGNORE_CH:
            raise ValueError(f"DAC channel {ch} is forbidden.")
        this_dac_ch = DAC_CH(ch,self.dac_device, max_v=max_v)
        this_dac_ch.v = v
        self.dac_ch_list[ch] = this_dac_ch
        return this_dac_ch
    
    def _write_dac_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],DAC_CH) and not key.startswith('_'):
                self.__dict__[key].key = key
                self.__dict__[key].set_errmessage()

    def dac_by_ch(self,ch) -> DAC_CH:
        return self.dac_ch_list[ch]
        
    @kernel
    def set(self,ch,v,load_dac=True):
        self.dac_device.write_dac(channel=ch,voltage=v)
        if load_dac:
            self.dac_device.load()
            
    @kernel
    def load(self):
        self.dac_device.load()

    def _fill_dac_list(self):
        assigned_ch = []
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],DAC_CH) and not key.startswith('_'):
                assigned_ch.append(self.__dict__[key].ch)
        for ch in CH_IDX:
            if ch not in assigned_ch:
                this_dac = DAC_CH(ch, self.dac_device)
                this_dac.key = f"dac_ch{ch}"
                self.dac_ch_list[ch] = this_dac
                vars(self)[this_dac.key] = this_dac
        

