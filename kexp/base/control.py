import numpy as np

from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from artiq.language.core import now_mu
from waxx.control.artiq.dummy_core import DummyCore

from waxx.control.raman_beams import RamanBeamPair

from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams
from kexp.config.data_vault import DataVault
from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.awg_tweezer import tweezer
from kexp.control.painted_lightsheet import lightsheet
from waxx.control.integrator import Integrator
from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_client import HMRClient
from waxx.control.misc.oscilloscopes import ScopeData

dv = -0.1
dvlist = np.linspace(1.,1.,5)

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2, tweezer_vpd2_to_vpd1

class Control():
    def __init__(self):
        # just to get syntax highlighting, placeholders
        self.core = DummyCore()
        self.data = DataVault()
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.params = ExptParams()
        self.scope_data = ScopeData()
        self.p = self.params