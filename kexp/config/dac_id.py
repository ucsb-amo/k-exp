import numpy as np
from artiq.experiment import kernel
from artiq.coredevice.zotino import Zotino

from waxx.config.dac_id import dac_frame as dac_frame_waxx
from waxx.control.artiq.DAC_CH import DAC_CH
from kexp.config.expt_params import ExptParams
from kexp.util.db.device_db import device_db

FORBIDDEN_CH = []
N_CH = 32

class dac_frame(dac_frame_waxx):
    def __init__(self, expt_params = ExptParams(), dac_device = Zotino):

        self.setup(expt_params, dac_device, N_CH)
        self.dac_device: Zotino
        self.p: ExptParams

        self.test = self.assign_dac_ch(0)

        self.cleanup()