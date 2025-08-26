import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.ttl import TTLOut, TTLInOut
from kexp.control.artiq.TTL import TTL, TTL_IN, TTL_OUT

import importlib.util

# IGNORE_IDX = range(40,48)
# N_ttl = 88
IGNORE_IDX = []
N_ttl = 8
TTL_IDX = list(np.array(range(N_ttl))[ [idx not in IGNORE_IDX for idx in range(N_ttl)] ] )

from kexp.util.db.device_db_test import device_db as DEVICE_DB

def get_ttl_class_by_key(key):
    # Find the device in the db by key and return the correct class
    dev = DEVICE_DB.get(key)
    if dev is None:
        return TTL_OUT  # fallback
    dev_class = dev.get("class")
    if dev_class == "TTLInOut":
        return TTL_IN
    elif dev_class == "TTLOut":
        return TTL_OUT
    else:
        return TTL_OUT  # fallback

class ttl_frame():
    def __init__(self):

        self.ttl_list = [TTL(0) for _ in range(N_ttl)]
        
        self.test = self.assign_ttl_out(4)
        self.test_2 = self.assign_ttl_out(5)
        self.line_trigger = self.assign_ttl_in(0)

        self._write_ttl_keys()
        self._fill_ttl_list()

        self.camera = TTL

    def assign_ttl_out(self,ch) -> TTL_OUT:
        this_ttl = TTL_OUT(ch)
        self.ttl_list[ch] = this_ttl
        return this_ttl
    
    def assign_ttl_in(self,ch) -> TTL_IN:
        this_ttl = TTL_IN(ch)
        self.ttl_list[ch] = this_ttl
        return this_ttl
    
    def ttl_by_ch(self,ch) -> TTL:
        return self.ttl_list[ch]
    
    def _write_ttl_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],TTL) and not key.startswith('_'):
                self.__dict__[key].key = key

    def _fill_ttl_list(self):
        assigned_ch = []
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],TTL) and not key.startswith('_'):
                assigned_ch.append(self.__dict__[key].ch)
        for ch in TTL_IDX:
            if ch not in assigned_ch:
                # Try to match the key in device_db and assign correct class
                ttl_key = f"ttl{ch}"
                ttl_class = get_ttl_class_by_key(ttl_key)
                this_ttl = ttl_class(ch)
                this_ttl.key = ttl_key
                self.ttl_list[ch] = this_ttl
                vars(self)[ttl_key] = this_ttl


