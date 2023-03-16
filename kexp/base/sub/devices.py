from artiq.experiment import *
from artiq.experiment import delay

from kexp.config.dds_id import dds_frame
from kexp.control.artiq.DDS import DDS

class devices():
    def __init__(self):
        pass

    @kernel
    def set_all_dds(self, state=0):
        for dds in self.dds_list:
            dds.set_dds()
            if state == 0:
                dds.off()
            elif state == 1:
                dds.on()
            delay(10*us)

    def prepare_devices(self):

        self.core = self.get_device("core")
        self.zotino = self.get_device("zotino0")

        self.dds = dds_frame()
        self.dds.get_dds_devices(self)

        self.dac_ch_3Dmot_current_control = 0

        self.ttl_camera = self.get_device("ttl4")

        self.dds_list = self.dds.dds_list()
    
