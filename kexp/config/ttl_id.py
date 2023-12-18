import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.ttl import TTLOut
from kexp.control.artiq.TTL import TTL

class ttl_frame():
    def __init__(self):

        self.ttl_list = []

        self.awg = self.ttl_assign(8)
        self.basler = self.ttl_assign(9)
        self.lightsheet_sw = self.ttl_assign(10)
        self.magnets = self.ttl_assign(11)
        self.spectrum_trig = self.ttl_assign(12)
        self.andor = self.ttl_assign(13)
        self.pd_scope_trig = self.ttl_assign(14)
        self.machine_table_trig = self.ttl_assign(25)

        self._write_ttl_keys()

        self.camera = TTL

    def ttl_assign(self,ch) -> TTL:
        this_ttl = TTL(ch)
        self.ttl_list.append(this_ttl)
        return this_ttl
    
    def _write_ttl_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],TTL):
                self.__dict__[key].key = key