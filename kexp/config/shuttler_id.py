import numpy as np
from artiq.experiment import kernel, portable

from artiq.coredevice.zotino import Zotino
from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from waxx.config.shuttler_id import shuttler_frame as shuttler_frame_waxx
from waxx.control.artiq.Shuttler_CH import Shuttler_CH

class shuttler_frame(shuttler_frame_waxx):
    def __init__(self):

        ### Setup

        self.setup()

        ### Channel assignment

        self.tweezer_mod = self._assign_ch(1)

        ###

        self.cleanup()