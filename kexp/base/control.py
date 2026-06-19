import numpy as np

from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential, at_mu
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

class Control():
    def __init__(self):
        # just to get syntax highlighting, placeholders
        self.core = DummyCore()
        self.data = DataVault()
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.params = ExptParams()
        self.raman = RamanBeamPair()
        self.scope_data = ScopeData()
        self.p = self.params

    @kernel
    def arm_scopes(self):
        self.core.wait_until_mu(now_mu())
        self.scope_data.arm()
        self.core.break_realtime()

    # @kernel
    # def background_field(self):
    #     if self.outer_coil.i_supply != 0.:
    #         self.outer_coil.off()
    #     if self.inner_coil.i_supply != 0.:
    #         self.inner_coil.off()
    #     self.set_shims(0.,0.,0.)
    #     self.dac.supply_current_2dmot.set(0.)
    #     delay(10.e-3)

    @kernel
    def prep_raman(self,
            frequency_transition=dv,
            fraction_power=dv,
            global_phase=0.,relative_phase=0.,
            t_phase_origin_mu=np.int64(-1),
            phase_mode=1,
            line_trigger=True):
        
        if frequency_transition == dv:
            frequency_transition = self.p.frequency_raman_transition
        if fraction_power == dv:
            fraction_power = self.p.fraction_power_raman
            
        self.raman.init(frequency_transition,
                        fraction_power,
                        global_phase,
                        relative_phase,
                        t_phase_origin_mu,
                        phase_mode)
        
        # self.ttl.raman_shutter.on()
        delay(3.e-3)
        # self.ttl.line_trigger.wait_for_line_trigger()
        # delay(4.7e-3)
        if phase_mode == 1:
            self.raman.set_phase(t_phase_origin_mu=now_mu())
        

        