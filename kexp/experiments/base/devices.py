from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

from kexp.util.artiq.expt_params import ExptParams
from kexp.config.dds_state import defaults as default_dds

class devices():
    def __init__(self):
        pass

    @kernel
    def set_all_dds(self, state=0):
        for dds in self.dds.values():
            dds.set_dds()
            if state == 0:
                dds.off()
            elif state == 1:
                dds.on()
            delay(10*us)

    def prepare_devices(self, dds_list = default_dds):

        self.core = self.get_device("core")
        self.zotino = self.get_device("zotino0")

        self.dds = dict()
        for dds in dds_list:
            dds.dds_device = self.get_device(dds.name())
            self.dds[dds.varname] = dds

        self.dac_ch_3Dmot_current_control = 0

        self.ttl_camera = self.get_device("ttl4")
    
