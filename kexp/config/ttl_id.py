import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.ttl import TTLOut, TTLInOut

from waxx.config.ttl_id import ttl_frame as ttl_frame_waxx
from waxx.control.artiq.TTL import TTL, TTL_IN, TTL_OUT

from kexp.util.db.device_db import device_db

N_TTL = 8

class ttl_frame(ttl_frame_waxx):
    def __init__(self):

        self._db = device_db

        self.setup(N_TTL)
        
        self.test = self.assign_ttl_out(0)

        self.cleanup()