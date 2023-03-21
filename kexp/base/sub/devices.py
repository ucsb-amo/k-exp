from artiq.experiment import *
from artiq.experiment import delay, delay_mu

from kexp.config.dds_id import dds_frame
from kexp.control.artiq.DDS import DDS
from kexp.config.expt_params import ExptParams

t_rtio_mu = ExptParams().t_rtio_mu

class devices():

    def __init__(self):
        pass

    def prepare_devices(self):

        self.core = self.get_device("core")
        self.zotino = self.get_device("zotino0")

        self.dds = dds_frame()
        self.dds.get_dds_devices(self)
        self.dds_list = self.dds.dds_list()

        self.dac_ch_3Dmot_current_control = 0

        self.ttl_camera = self.get_device("ttl4")

    @kernel
    def init_kernel(self):
        self.core.reset()
        self.zotino.init()
        delay_mu(t_rtio_mu)
        self.init_all_cpld()
        self.set_all_dds(0)
        self.core.break_realtime()

    @kernel
    def set_all_dds(self, state):
        for dds in self.dds_list:
            dds.set_dds()
            if state == 0:
                dds.off()
            elif state == 1:
                dds.on()
            delay_mu(t_rtio_mu)

    @kernel
    def init_all_cpld(self):
        for dds in self.dds_list:
            dds.dds_device.cpld.init()
            delay(1*ms)
    
