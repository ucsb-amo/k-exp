import numpy as np

from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from artiq.language.core import now_mu

from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams

dv = -0.1
dvlist = np.linspace(1.,1.,5)

class Control():
    def __init__(self):
        # just to get syntax highlighting, placeholders
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.params = ExptParams()
        self.p = self.params