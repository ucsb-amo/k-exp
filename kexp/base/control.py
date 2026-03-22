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
        self.inner_coil = hbridge_magnet()
        self.outer_coil = igbt_magnet()
        self.tweezer = tweezer()
        self.lightsheet = lightsheet()
        self.params = ExptParams()
        self.raman = RamanBeamPair()
        self.raman_nf = RamanBeamPair()
        self.magnetometer = HMRClient()
        self.integrator = Integrator()
        self.scope_data = ScopeData()
        self.p = self.params

    @kernel
    def tof_apd_abs_image(self):

        self.tweezer.off()
        delay(self.p.t_tof_apd_abs)
        
        t = self.p.t_imaging_pulse_apd_abs
        dc = self.data.post_shot_absorption

        self.integrated_imaging_pulse(dc,t,0)
        delay(1.e-6)
        self.raman.pulse(self.p.t_raman_pi_pulse)
        delay(2.e-6)
        self.integrated_imaging_pulse(dc,t,1)
        delay(200.e-6)
        self.integrated_imaging_pulse(dc,t,2)
        delay(10.e-6)
        self.integrated_imaging_pulse(dc,t,3,dark=True)

    @kernel
    def integrated_imaging_pulse(self,data_container,t=dv,idx=0,dark=False):
        if t == dv:
            t = self.p.t_imaging_pulse_apd_abs
        self.integrator.begin_integrate()
        if dark:
            delay(t)
        else:
            self.imaging.pulse(t)
        data_container.put_data_idx( self.integrator.stop_and_sample(), idx )
        # data_container.shot_data[idx] = 
        self.integrator.clear()

    @kernel
    def tweezer_squeeze(self):
        self.tweezer.paint_amp_dac.set(-7.)
        
        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_1,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
                          v_end=self.p.v_pd_tweezer_squeeze_rampup_handoff_lp,
                          low_power=True, paint=False, keep_trap_frequency_constant=False)

        self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_2,
                          v_start=tweezer_vpd2_to_vpd1(self.p.v_pd_tweezer_squeeze_rampup_handoff_lp),
                          v_end=self.p.v_pd_hf_tweezer_squeeze_power,
                          paint=False,keep_trap_frequency_constant=False)
        
    @kernel
    def reset_tweezers(self, two_d_tweezers):
        if self._setup_awg:
            if two_d_tweezers:
                self.tweezer.set_static_2d_tweezers(freq_list1=self.params.frequency_tweezer_list1,
                                                    freq_list2=self.params.frequency_tweezer_list2,
                                                    amp_list1=self.params.amp_tweezer_list1,
                                                    amp_list2=self.params.amp_tweezer_list2)
            self.tweezer.reset_traps(self.xvarnames)
            delay(100.e-3)
            self.tweezer.awg_trg_ttl.pulse(t=1.e-6)
        
        self.tweezer.pid1_int_hold_zero.pulse(1.e-6)
        self.tweezer.pid1_int_hold_zero.on()

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

        self.inner_coil.stop_pid()
        self.inner_coil.off()
        self.inner_coil.discharge()

    @kernel
    def arm_scopes(self):
        self.core.wait_until_mu(now_mu())
        self.scope_data.arm()
        self.core.break_realtime()

    @kernel
    def background_field(self):
        if self.outer_coil.i_supply != 0.:
            self.outer_coil.off()
        if self.inner_coil.i_supply != 0.:
            self.inner_coil.off()
        self.set_shims(0.,0.,0.)
        self.dac.supply_current_2dmot.set(0.)
        delay(10.e-3)

    @kernel
    def read_magnetometer(self):
        self.core.wait_until_mu(now_mu())
        b_magnitude = self.magnetometer.get_field_magnitude()
        self.data.b.put_data_idx(b_magnitude,0)
        self.core.break_realtime()

    @kernel
    def prep_raman(self, frequency_raman = dv):
        
        if frequency_raman == dv:
            frequency_raman = self.p.frequency_raman_transition

        self.raman.init(frequency_transition = frequency_raman, 
                        fraction_power = self.params.fraction_power_raman)
        
        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)