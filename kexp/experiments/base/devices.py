from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

from kexp.util.artiq.expt_params import ExptParams
from kexp.config.dds_state import defaults as default_dds

@kernel
def set_all_dds(expt, state=0):
    for dds in expt.dds.values():
        dds.set_dds()
        if state == 0:
            dds.off()
        elif state == 1:
            dds.on()
        delay(10*us)

def prepare_devices(expt, dds_list=default_dds):

    expt.core = expt.get_device("core")
    expt.zotino = expt.get_device("zotino")

    expt.dds = dict()
    for dds in dds_list:
        dds.dds_device = expt.get_device(dds.name())
        expt.dds[dds.varname] = dds

    expt.dac_ch_3Dmot_current_control = 0

    expt.ttl_camera = expt.get_device("ttl4")
