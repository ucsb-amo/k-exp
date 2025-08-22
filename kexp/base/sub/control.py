from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from artiq.language.core import now_mu
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.control.misc.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.misc.awg_tweezer import tweezer
from kexp.control.misc.painted_lightsheet import lightsheet
from kexp.control.misc.raman_beams import RamanBeamPair
from kexp.config.expt_params import ExptParams
import numpy as np

from kexp.util.artiq.async_print import aprint

dv = -0.1
dvlist = np.linspace(1.,1.,5)

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

class Control():
    def __init__(self):
        # just to get syntax highlighting
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.inner_coil = hbridge_magnet()
        self.outer_coil = igbt_magnet()
        self.tweezer = tweezer()
        self.lightsheet = lightsheet()
        self.params = ExptParams()
        self.raman = RamanBeamPair()
        self.p = self.params

    @kernel
    def init_raman_beams(self,frequency_transition=dv,amp_raman=dv,
                         global_phase=0.,relative_phase=0.,
                         t_phase_origin_mu=np.int64(-1),
                         phase_mode=1):
        if t_phase_origin_mu < 0:
            t_phase_origin_mu = now_mu()
        self.raman.set(frequency_transition,amp_raman,
                       global_phase,relative_phase,
                       t_phase_origin_mu=t_phase_origin_mu,
                       phase_mode=phase_mode,
                       init=True)

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
        self.outer_coil.off()
        self.outer_coil.discharge()
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

        self.inner_coil.stop_pid()
        self.inner_coil.off()
        self.inner_coil.discharge()

        self.ttl.d2_mot_shutter.off()