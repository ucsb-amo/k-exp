import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.ttl import TTLOut
from kexp.control.artiq.TTL import TTL

class ttl_frame():
    def __init__(self):

        self.ttl_list = []

        self.lightsheet_sw = self.ttl_assign(4)
        self.xy_basler = self.ttl_assign(5)
        self.inner_coil_igbt = self.ttl_assign(6)
        self.andor = self.ttl_assign(7)
        self.outer_coil_igbt = self.ttl_assign(8)
        self.hbridge_helmholtz = self.ttl_assign(9)
        self.z_basler = self.ttl_assign(10)
        self.tweezer_pid_int_zero = self.ttl_assign(11)
        self.lightsheet_pid_int_zero = self.ttl_assign(12)
        self.awg = self.ttl_assign(13)
        self.awg_trigger = self.ttl_assign(14)
        self.pd_scope_trig = self.ttl_assign(16)
        self.pd_scope_trig_2 = self.ttl_assign(17)
        # self.machine_table_trig = self.ttl_assign(25)

        self.coil_contactor_placeholder = self.ttl_assign(39)

        self._write_ttl_keys()

        self.camera = TTL

    def ttl_assign(self,ch) -> TTL:
        this_ttl = TTL(ch)
        self.ttl_list.append(this_ttl)
        return this_ttl
    
    def ttl_by_ch(self,ch) -> TTL:
        ch_list = [ttl.ch for ttl in self.ttl_list]
        if ch in ch_list:
            ch_idx = ch_list.index(ch)
            return self.ttl_list[ch_idx]
        else:
            raise ValueError(f"DAC ch {ch} not assigned in dac_id.")
    
    def _write_ttl_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],TTL):
                self.__dict__[key].key = key
                