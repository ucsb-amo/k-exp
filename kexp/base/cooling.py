from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential

from waxx.control.raman_beams import RamanBeamPair

from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams
from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.awg_tweezer import tweezer
from kexp.control.painted_lightsheet import lightsheet

import numpy as np

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2, tweezer_vpd2_to_vpd1

dv = 100.
dvlist = np.linspace(1.,1.,5)

from kexp.util.artiq.async_print import aprint

class Cooling():
    def __init__(self):
        # just to get syntax highlighting
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.params = ExptParams()
        self.raman = RamanBeamPair()
        self.p = self.params