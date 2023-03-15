from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

from kexp.util.artiq.expt_params import ExptParams
from kexp.config.dds_state import defaults as default_dds

def read_dds_from_config(expt, dds_params=default_dds):
    expt.dds = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
    for dds0 in dds_params:
        dds0.dds_device = expt.get_device(dds0.name())
        expt.dds[dds0.urukul_idx][dds0.ch] = dds0

@kernel
def set_all_dds(self,state=0):
    for dds_sublist in self.dds:
        for dds in dds_sublist:
            dds.set_dds()
            if state == 0:
                dds.off()
            elif state == 1:
                dds.on()
            delay(10*us)

def assign_channels(self,expt,dds_list):

    read_dds_from_config(expt)

    expt.core = self.get_device("core")
    expt.zotino = expt.get_device("zotino")

    expt.dds_push = dds_list[0][0]
    expt.dds_d2_2d_r = dds_list[0][1]
    expt.dds_d2_2d_c = dds_list[0][2]
    expt.dds_d2_3d_r = dds_list[0][3]
    expt.dds_d2_3d_c = dds_list[1][0]
    expt.dds_d1_3d_r = dds_list[1][2] 
    expt.dds_d1_3d_c = dds_list[1][3]
    expt.dds_imaging = dds_list[1][1]

    expt.dac_ch_3Dmot_current_control = 0

    self.ttl_camera = self.get_device("ttl4")

def prepare_devices(expt):
    read_dds_from_config(expt)
    assign_channels(expt)
