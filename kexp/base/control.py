import numpy as np

from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from artiq.language.core import now_mu

from waxx.control.raman_beams import RamanBeamPair

from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams
from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.awg_tweezer import tweezer
from kexp.control.painted_lightsheet import lightsheet

dv = -0.1
dvlist = np.linspace(1.,1.,5)

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

class Control():
    def __init__(self):
        # just to get syntax highlighting, placeholders
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.inner_coil = hbridge_magnet()
        self.outer_coil = igbt_magnet()
        self.tweezer = tweezer()
        self.lightsheet = lightsheet()
        self.params = ExptParams()
        self.raman = RamanBeamPair()
        self.raman_nf = RamanBeamPair()
        self.p = self.params

    @kernel
    def reset_coils(self):
        """
        Reset the inner, outer, and 2D coils to their default state.
        This includes stopping any PID control, turning off the coils,
        and discharging the power supplies through the coils.

        This is typically called at the end of an experiment to ensure
        that the coils are in a safe state for the next experiment.
        """
    
        self.outer_coil.stop_pid()
        delay(50.e-3)
        self.outer_coil.off()
        self.outer_coil.discharge()
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

        self.inner_coil.stop_pid()
        self.inner_coil.off()
        self.inner_coil.discharge()