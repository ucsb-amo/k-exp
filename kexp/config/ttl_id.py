import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.ttl import TTLOut, TTLInOut

from waxx.config.ttl_id import ttl_frame as ttl_frame_waxx
from waxx.control.artiq.TTL import TTL, TTL_IN, TTL_OUT

class ttl_frame(ttl_frame_waxx):
    def __init__(self):

        self.setup()
        
        self.test = self.assign_ttl_out(4)
        self.test_2 = self.assign_ttl_out(5)
        self.line_trigger = self.assign_ttl_in(0)

        self.cleanup()