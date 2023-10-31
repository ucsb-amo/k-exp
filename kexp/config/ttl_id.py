import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.ttl import TTLOut
from kexp.control.artiq.TTL import TTL

class ttl_frame():
    def __init__(self):

        self.ttl_list = []

        self.ttl_basler = self.ttl_assign(9)
        self.ttl_magnets = self.ttl_assign(11)
        self.ttl_andor = self.ttl_assign(13)
        self.ttl_trig = self.ttl_assign(14)

        self._write_ttl_keys()

        self.ttl_camera = TTL

    def ttl_assign(self,ch) -> TTL:
        this_ttl = TTL(ch)
        self.ttl_list.append(this_ttl)
        return
    
    def _write_ttl_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],TTL):
                self.__dict__[key].key = key