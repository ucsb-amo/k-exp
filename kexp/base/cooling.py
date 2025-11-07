from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams

from kexp.control.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.awg_tweezer import tweezer
from kexp.control.painted_lightsheet import lightsheet
from kexp.control.raman_beams import RamanBeamPair

import numpy as np

dv = 100.
dvlist = np.linspace(1.,1.,5)

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

class Cooling():
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

    ## meta stages
    # @kernel
    # def warmup(self,N=5):
    #     for _ in range(N):
    #         self.core.break_realtime()
    #         self.prepare_lf_tweezers()
    #         self.tweezer.off()

    @kernel
    def prepare_hf_tweezers(self):
        """prepares hf evap tweezers at i_outer = ExptParams.i_spin_mixture with
        PID enabled.
        """   
        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_lightsheet_evap1_current,
                             i_end=self.p.i_hf_tweezer_load_current)
    
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
                          
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown2_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)

        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_load_current,
                             i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_evap1_current,
                             i_end=self.p.i_hf_tweezer_evap2_current)
        
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_end=self.p.i_non_inter)

        self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
                                               v_start=self.dac.tweezer_paint_amp.v,
                                               v_end=self.p.v_hf_paint_amp_end,
                                               n=1000)
        
        delay(100.e-3)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()

        self.ttl.d2_mot_shutter.off()

        delay(40.e-3)

    @kernel
    def prepare_lf_tweezers(self):
        """prepares lf evap tweezers at i_outer = ExptParams.i_spin_mixture with
        PID enabled.
        """        

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,
                                                   self.p.v_yshim_current_magtrap,
                                                   0.,n=500)

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lf_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_lightsheet_evap1_current,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_lf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lf_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown3_end)
        
        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_lf_tweezer_evap1_current)
        
        # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_lf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_evap1_current,
                             i_end=self.p.i_lf_tweezer_evap2_current)
        
        # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_lf_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_start=self.p.i_lf_tweezer_evap2_current,
                             i_end=self.p.i_spin_mixture)
        
        self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
                                               v_start=self.dac.tweezer_paint_amp.v,
                                               v_end=self.p.v_paint_amp_end,
                                               n=1000)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()

        self.ttl.d2_mot_shutter.off()

        delay(40.e-3)

    ## cooling stages

    @kernel
    def flash_repump(self,t=dv,detune=dv,amp=dv):
        if t == dv:
            t = self.params.t_repump_flash_imaging
        if detune == dv:
            detune = self.params.detune_d2_r_imaging
        if amp == dv:
            amp = self.params.amp_d2_r_imaging

        self.dds.d2_3d_r.set_dds_gamma(delta=detune,amplitude=amp)
        self.dds.d2_3d_r.on()
        delay(t)
        self.dds.d2_3d_r.off()

    @kernel
    def pump_to_F1(self,t=dv,
                   v_zshim_current = dv,
                   v_yshim_current = dv,
                   v_xshim_current = dv):

        if t == dv:
            t = self.params.t_pump_to_F1
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current_magtrap
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current_magtrap
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current_magtrap

        self.set_shims(v_zshim_current=self.params.v_zshim_current_magtrap,
                        v_yshim_current=self.params.v_yshim_current_magtrap,
                        v_xshim_current=self.params.v_xshim_current_magtrap)
        delay(2.e-3)
        self.dds.optical_pumping.set_dds()
        self.dds.optical_pumping.on()
        delay(t)
        self.dds.optical_pumping.off()
        self.flash_cooler()

    @kernel
    def flash_cooler(self,t=dv,detune=dv,amp=dv):
        if t == dv:
            t = self.params.t_cooler_flash_imaging
        if detune == dv:
            detune = self.params.detune_d2_c_imaging
        if amp == dv:
            amp = self.params.amp_d2_c_imaging


        self.dds.d2_3d_c.set_dds_gamma(delta=detune,amplitude=amp)
        self.dds.d2_3d_c.on()
        delay(t)
        self.dds.d2_3d_c.off()

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.push.off()
            self.switch_d2_3d(0)
            self.inner_coil.off()
        delay(t)

    @kernel
    def load_2D_mot(self, t,
                     detune_d2_vc = dv,
                     amp_d2_vc = dv,
                     detune_d2_vr = dv,
                     amp_d2_vr = dv,
                     detune_d2_hc = dv,
                     amp_d2_hc = dv,
                     detune_d2_hr = dv,
                     amp_d2_hr = dv,
                     detune_push = dv,
                     amp_push = dv,
                     v_analog_supply = dv,
                     with_push = True):
        
        ### Start Defaults ###
        if detune_d2_vc == dv:
            detune_d2_vc = self.params.detune_d2v_c_2dmot
        if amp_d2_vc == dv:
            amp_d2_vc = self.params.amp_d2v_c_2dmot
        if detune_d2_vr == dv:
            detune_d2_vr = self.params.detune_d2v_r_2dmot
        if amp_d2_vr == dv:
            amp_d2_vr = self.params.amp_d2v_r_2dmot
        if detune_d2_hc == dv:
            detune_d2_hc = self.params.detune_d2h_c_2dmot
        if amp_d2_hc == dv:
            amp_d2_hc = self.params.amp_d2h_c_2dmot
        if detune_d2_hr == dv:
            detune_d2_hr = self.params.detune_d2h_r_2dmot
        if amp_d2_hr == dv:
            amp_d2_hr = self.params.amp_d2h_r_2dmot
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if v_analog_supply == dv:
            v_analog_supply = self.params.v_2d_mot_current
        ### End Defaults ###

        self.dds.d2_2dh_c.set_dds_gamma(delta=detune_d2_hc,
                                 amplitude=amp_d2_hc)
        self.dds.d2_2dh_r.set_dds_gamma(delta=detune_d2_hr,
                                 amplitude=amp_d2_hr)
        self.dds.d2_2dv_c.set_dds_gamma(delta=detune_d2_vc,
                                 amplitude=amp_d2_vc)
        self.dds.d2_2dv_r.set_dds_gamma(delta=detune_d2_vr,
                                 amplitude=amp_d2_vr)
        delay(self.params.t_rtio)
        if with_push:
            self.dds.push.set_dds_gamma(delta=detune_push,
                                    amplitude=amp_push)
        else:
            self.dds.push.off()
        
        self.dac.supply_current_2dmot.set(v=v_analog_supply)

        with parallel:
            self.switch_d2_2d(1)
        delay(t)

    @kernel
    def mot(self,t,
            detune_d2_c = dv,
            amp_d2_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            detune_push = dv,
            amp_push = dv,
            i_supply = dv,
            v_zshim_current = dv,
            v_yshim_current = dv,
            v_xshim_current = dv):
        
        ### Start Defaults ###
        if detune_d2_c == dv:
            detune_d2_c = self.params.detune_d2_c_mot
        if amp_d2_c == dv:
            amp_d2_c = self.params.amp_d2_c_mot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_mot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_mot
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if i_supply == dv:
            i_supply = self.params.i_mot
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current
        ### End Defaults ###

        delay(1.e-3)

        self.ttl.d2_mot_shutter.on()

        delay(1.e-3)
            
        self.inner_coil.set_supply(i_supply)
        self.inner_coil.set_voltage(20.)
        self.inner_coil.on()

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay(self.params.t_rtio)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay(self.params.t_rtio)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        
        self.ttl.zshim_hbridge_flip.off()
        
        self.set_shims(v_xshim_current,v_yshim_current,v_zshim_current)
        with parallel:
            self.switch_d2_3d(1)
            self.dds.push.on()
        delay(t)

    @kernel
    def mot_reload(self,t,
            detune_d2_c = dv,
            amp_d2_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            i_supply = dv,
            v_zshim_current = dv):
        
        ### Start Defaults ###
        if detune_d2_c == dv:
            detune_d2_c = self.params.detune_d2_c_mot
        if amp_d2_c == dv:
            amp_d2_c = self.params.amp_d2_c_mot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_mot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_mot
        if i_supply == dv:
            i_supply = self.params.i_mot
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current
        ### End Defaults ###
            
        self.inner_coil.set_supply(i_supply)
        self.inner_coil.set_voltage(i_supply)
        self.inner_coil.on()
        
        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay(self.params.t_rtio)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        self.set_shims()
        self.switch_d2_3d(1)
        delay(t)

    @kernel
    def hybrid_mot(self,t,
            detune_d2_c = dv,
            amp_d2_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            detune_d1_c = dv,
            v_pd_d1_c = dv,
            detune_d1_r = dv,
            v_pd_d1_r = dv,
            i_supply = dv,
            v_zshim_current = dv):
        
        ### Start Defaults ###
        if detune_d2_c == dv:
            detune_d2_c = self.params.detune_d2_c_mot
        if amp_d2_c == dv:
            amp_d2_c = self.params.amp_d2_c_mot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_mot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_mot
        ### End Defaults ###

        if detune_d1_c == dv:
            detune_d1_c = self.params.detune_d1_c_mot
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_mot
        if detune_d1_r == dv:
            detune_d1_r = self.params.detune_d1_r_mot
        if v_pd_d1_r == dv:
            v_pd_d1_r = self.params.v_pd_d1_r_mot

        if i_supply == dv:
            i_supply = self.params.i_mot
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current

        self.inner_coil.set_supply(i_supply)
        self.inner_coil.set_voltage(i_supply)
        self.inner_coil.on()

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay(self.params.t_rtio)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay(self.params.t_rtio)
        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                 v_pd=v_pd_d1_c)
        delay(self.params.t_rtio)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r,
                                 v_pd=v_pd_d1_r)
        self.set_shims()
        with parallel:
            self.switch_d2_3d(1)
            self.dds.push.on()
        self.switch_d1_3d(1)
        delay(t)

    #compress MOT by changing D2 detunings and raising B field
    @kernel
    def cmot_d2(self,t,
            detune_d2_c = dv,
            amp_d2_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            i_supply = dv):
        
        ### Start Defaults ###
        if detune_d2_c == dv:
            detune_d2_c = self.params.detune_d2_c_d2cmot
        if amp_d2_c == dv:
            amp_d2_c = self.params.amp_d2_c_d2cmot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_d2cmot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_d2cmot
        if i_supply == dv:
            i_supply = self.params.i_cmot
        ### End Defaults ###
            
        self.inner_coil.set_supply(i_supply)
        self.inner_coil.set_voltage(i_supply)
        self.inner_coil.on()

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                       amplitude=amp_d2_c)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                       amplitude=amp_d2_r)
        self.switch_d2_3d(1)
        delay(t)

    #hybrid compressed MOT with only D2 repump and D1 cooler, setting B field to lower value
    @kernel
    def cmot_d1(self,t,
            detune_d1_c = dv,
            v_pd_d1_c = dv,
            amp_d1_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            i_supply = dv):
        
        ### Start Defaults ###
        if detune_d1_c == dv:
            detune_d1_c = self.params.detune_d1_c_d1cmot
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_d1cmot
        if amp_d1_c == dv:
            amp_d1_c = self.params.amp_d1_3d_c
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_d1cmot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_d1cmot
        if i_supply == dv:
            i_supply = self.params.i_cmot
        ### End Defaults ###
            
        # self.inner_coil.set_supply(i_supply)
        self.inner_coil.set_supply(self.params.i_magtrap_init)
        # self.inner_coil.set_voltage(i_supply)
        # self.inner_coil.on()

        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                       v_pd=v_pd_d1_c)
        delay(self.params.t_rtio)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                       amplitude=amp_d2_r)

        # with parallel:
        self.dds.d2_3d_r.on()
        self.dds.d1_3d_c.on()
        delay(self.params.t_rtio)
        self.dds.d2_3d_c.off()
        self.dds.d1_3d_r.off()
        
        delay(t)

    @kernel
    def cmot_d1_sweep(self,t,
            v_pd_d1_c = dv,
            amp_d1_c = dv,
            amp_d2_r = dv,
            i_supply = dv):
        
        ### Start Defaults ###
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_d1cmot
        if amp_d1_c == dv:
            amp_d1_c = self.params.amp_d1_3d_c
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_d1cmot
        if i_supply == dv:
            i_supply = self.params.i_cmot
        ### End Defaults ###

        # self.inner_coil.set_supply(i_supply)
        self.inner_coil.set_supply(self.params.i_magtrap_init)
        # self.inner_coil.set_voltage(i_supply)
        # self.inner_coil.on()

        n = self.params.n_d1cmot_detuning_sweep_steps
        dt = t / n

        delta_d1_c_0 = self.params.detune_d1_c_sweep_d1cmot_start
        delta_d1_c_f = self.params.detune_d1_c_sweep_d1cmot_end
        df_c = (delta_d1_c_f - delta_d1_c_0)/(n-1)

        delta_d2_r_0 = self.params.detune_d2_r_sweep_d1cmot_start
        delta_d2_r_f = self.params.detune_d2_r_sweep_d1cmot_end
        df_r = (delta_d2_r_f - delta_d2_r_0)/(n-1)

        self.dds.d1_3d_c.set_dds_gamma(delta=delta_d1_c_0,
                                       v_pd=v_pd_d1_c)
        self.dds.d2_3d_r.set_dds_gamma(delta=delta_d2_r_0,
                                       amplitude=amp_d2_r)

        # with parallel:
        self.dds.d2_3d_r.on()
        self.dds.d1_3d_c.on()

        for i in range(n):
            self.dds.d1_3d_c.set_dds_gamma(delta= delta_d1_c_0 + i*df_c)
            self.dds.d2_3d_r.set_dds_gamma(delta= delta_d2_r_0 + i*df_r)
            delay(dt)

        self.dds.d2_3d_c.off()
        self.dds.d1_3d_r.off()

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t,
            detune_d1_c = dv,
            v_pd_d1_c = dv,
            amp_d1_c = dv,
            detune_d1_r = dv,
            v_pd_d1_r = dv,
            amp_d1_r = dv,
            detune_d1 = dv,
            t_shim_change_pretrigger = dv,
            t_magnet_off_pretrigger = dv,
            v_zshim_current=dv,
            v_yshim_current=dv,
            v_xshim_current=dv):
        
        ### Start Defaults ###
        if detune_d1 != dv:
            detune_d1_c = detune_d1
            detune_d1_r = detune_d1
        else:
            if detune_d1_c == dv:
                detune_d1_c = self.params.detune_d1_c_gm
            if detune_d1_r == dv:
                detune_d1_r = self.params.detune_d1_r_gm
        
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_gm
        if amp_d1_c == dv:
            amp_d1_c = self.params.amp_d1_3d_c
        if v_pd_d1_r == dv:
            v_pd_d1_r = self.params.v_pd_d1_r_gm
        if amp_d1_r == dv:
            amp_d1_r = self.params.amp_d1_3d_r
        if t_shim_change_pretrigger == dv:
            t_shim_change_pretrigger = self.params.t_shim_change_pretrigger
        if t_magnet_off_pretrigger == dv:
            t_magnet_off_pretrigger = self.params.t_magnet_off_pretrigger
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current_gm
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current_gm
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current_gm
        
        # ### End Defaults ###

        delay(-t_magnet_off_pretrigger)
        self.set_shims(v_zshim_current=v_zshim_current,
                        v_yshim_current=v_yshim_current,
                          v_xshim_current=v_xshim_current)
        delay(t_magnet_off_pretrigger)
       
        delay(-t_magnet_off_pretrigger)
        self.inner_coil.igbt_ttl.off()
        delay(t_magnet_off_pretrigger)

        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c, 
                                       amplitude=amp_d1_c,
                                       v_pd=v_pd_d1_c)
        delay(self.params.t_rtio)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
                                       amplitude=amp_d1_r,
                                       v_pd=v_pd_d1_r)
        with parallel:
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)
        delay(t)

    @kernel
    def gm_ramp(self, t_gmramp = dv,
            detune_d1_c = dv,
            v_pd_d1_c_list = dvlist,
            amp_d1_c = dv,
            detune_d1_r = dv,
            v_pd_d1_r_list = dvlist,
            amp_d1_r = dv,
            detune_d1 = dv):
        
        ### Start Defaults ###
        if detune_d1 != dv:
            detune_d1_c = detune_d1
            detune_d1_r = detune_d1
        else:
            if detune_d1_c == dv:
                detune_d1_c = self.params.detune_d1_c_gm
            if detune_d1_r == dv:
                detune_d1_r = self.params.detune_d1_r_gm

        if amp_d1_c == dv:
            amp_d1_c = self.params.amp_d1_3d_c
        if amp_d1_r == dv:
            amp_d1_r = self.params.amp_d1_3d_r
        
        if v_pd_d1_c_list == dvlist:
            v_pd_d1_c_list = self.params.v_pd_c_gmramp_list
        if v_pd_d1_r_list == dvlist:
            v_pd_d1_r_list = self.params.v_pd_r_gmramp_list

        # check for list length agreement
        N_elem = len(v_pd_d1_c_list)
        if N_elem != len(v_pd_d1_r_list):
            try: self.camera.Close()
            except: pass
            raise ValueError("GM ramp v_pd lists must be of the same length.")
        
        if t_gmramp == dv:
            t_gmramp = self.params.t_gmramp
            dt_gmramp = self.params.dt_gmramp
        else:
            dt_gmramp = t_gmramp / N_elem

        ### End Defaults ###

        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                       amplitude=amp_d1_c, 
                                       v_pd=v_pd_d1_c_list[0])
        delay(self.params.t_rtio)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
                                       amplitude=amp_d1_r,
                                       v_pd=v_pd_d1_r_list[0])

        self.switch_d1_3d(1)

        for n in range(N_elem):
            self.dds.d1_3d_c.set_dds(v_pd=v_pd_d1_c_list[n])
            delay(self.params.t_rtio)
            self.dds.d1_3d_r.set_dds(v_pd=v_pd_d1_r_list[n])
            delay(dt_gmramp)

    @kernel
    def optical_pumping(self, t,
                        t_bias_rampup=dv,
                        detune_optical_pumping=dv,
                        amp_optical_pumping=dv,
                        v_zshim_current=dv,
                        v_yshim_current=dv,
                        v_xshim_current=dv,
                        detune_optical_pumping_r=dv,
                        amp_optical_pumping_r=dv):
        
        if t_bias_rampup == dv:
            t_bias_rampup = self.params.t_optical_pumping_bias_rampup
        if detune_optical_pumping == dv:
            detune_optical_pumping = self.params.detune_optical_pumping_op
        if amp_optical_pumping == dv:
            amp_optical_pumping = self.params.amp_optical_pumping_op
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current_gm
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current_op
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current_op
        if detune_optical_pumping_r == dv:
            detune_optical_pumping_r = self.params.detune_optical_pumping_r_op
        if amp_optical_pumping_r == dv:
            amp_optical_pumping_r = self.params.amp_optical_pumping_r_op

        if t_bias_rampup:
            # delay(-t_bias_rampup)
            self.set_shims(v_zshim_current=v_zshim_current,
                           v_yshim_current=v_yshim_current,
                           v_xshim_current=v_xshim_current)
            delay(t_bias_rampup)
        self.dds.optical_pumping.set_dds_gamma(delta=detune_optical_pumping, 
                                       amplitude=amp_optical_pumping)
        self.dds.op_r.set_dds_gamma(delta=detune_optical_pumping_r,
                              amplitude=amp_optical_pumping_r)
        
        if t:
            self.dds.optical_pumping.on()
            self.dds.op_r.on()
            delay(t)
            self.dds.optical_pumping.off()
            self.dds.op_r.off()

    @kernel
    def start_magtrap(self,v_zshim_current=dv,
                        v_yshim_current=dv,
                        v_xshim_current=dv,
                        t_delay=dv):
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current_magtrap
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current_magtrap
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current_magtrap
        if t_delay == dv:
            t_delay = self.params.t_magtrap_delay
        
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.pump_to_F1(v_xshim_current=v_xshim_current,
                        v_yshim_current=v_yshim_current,
                        v_zshim_current=v_zshim_current)

        self.power_down_cooling()
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.ttl.d2_mot_shutter.on()

        delay(t_delay)
             
        # magtrap start
        self.inner_coil.on()

    @kernel
    def magtrap_and_load_lightsheet(self,
                                    do_lightsheet_ramp=True,
                                    do_magtrap_rampup=True,
                                    do_magtrap_hold=True,
                                    do_magtrap_rampdown=True,
                                    paint_lightsheet=False,
                                    t_lightsheet_ramp=dv,
                                    t_magtrap_ramp=dv,
                                    t_magtrap_rampdown=dv,
                                    v_pd_lightsheet_ramp_start=dv,
                                    v_pd_lightsheet_ramp_end=dv,
                                    v_awg_paint_amp_lightsheet=dv,
                                    i_magtrap_init=dv,
                                    i_magtrap_ramp_end=dv,
                                    v_zshim_current=dv,
                                    v_yshim_current=dv,
                                    v_xshim_current=dv):
        if t_lightsheet_ramp == dv:
            t_lightsheet_ramp = self.params.t_lightsheet_rampup
        if t_magtrap_ramp == dv:
            t_magtrap_ramp = self.params.t_magtrap_ramp
        if t_magtrap_rampdown == dv:
            t_magtrap_rampdown = self.params.t_magtrap_rampdown
        if v_pd_lightsheet_ramp_start == dv:
            v_pd_lightsheet_ramp_start = self.params.v_pd_lightsheet_rampup_start
        if v_pd_lightsheet_ramp_end == dv:
            v_pd_lightsheet_ramp_end = self.params.v_pd_lightsheet_rampup_end
        if v_awg_paint_amp_lightsheet == dv:
            v_awg_paint_amp_lightsheet = self.params.v_lightsheet_paint_amp_max
        if i_magtrap_init == dv:
            i_magtrap_init = self.params.i_magtrap_init
        if i_magtrap_ramp_end == dv:
            i_magtrap_ramp_end = self.params.i_magtrap_ramp_end
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current_magtrap
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current_magtrap
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current_magtrap

        self.start_magtrap(v_zshim_current=v_zshim_current,
                           v_yshim_current=v_yshim_current,
                           v_xshim_current=v_xshim_current)

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        delay(self.params.t_pre_lightsheet_rampup_delay)

        # ramp up lightsheet over magtrap
        if do_lightsheet_ramp:
            self.lightsheet.ramp(t_lightsheet_ramp,
                                v_pd_lightsheet_ramp_start,
                                v_pd_lightsheet_ramp_end,
                                paint=paint_lightsheet,
                                v_awg_am_max=v_awg_paint_amp_lightsheet,
                                keep_trap_frequency_constant=False)
        # else:
            # delay(t_lightsheet_ramp)

        if do_magtrap_rampup:
            self.inner_coil.ramp_supply(t=t_magtrap_ramp,
                                i_start=i_magtrap_init,
                                i_end=i_magtrap_ramp_end)
        # self.set_shims(v_zshim_current=0.)
        if do_magtrap_hold:
            delay(self.params.t_magtrap)

        if do_magtrap_rampdown:
            if do_magtrap_rampup:
                self.inner_coil.ramp_supply(t=t_magtrap_rampdown,
                                    i_start=i_magtrap_ramp_end,
                                    i_end=0.)
            else:
                self.inner_coil.ramp_supply(t=t_magtrap_rampdown,
                                    i_start=i_magtrap_init,
                                    i_end=0.)
            self.inner_coil.snap_off()

    @kernel
    def release(self):
        self.inner_coil.igbt_ttl.off()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

    ## AOM group control

    @kernel
    def switch_d2_2d(self,state):
        if state == 1:
            with parallel:
                self.dds.d2_2dh_c.on()
                self.dds.d2_2dh_r.on()
                self.dds.d2_2dv_c.on()
                self.dds.d2_2dv_r.on()
        elif state == 0:
            with parallel:
                self.dds.d2_2dh_c.off()
                self.dds.d2_2dh_r.off()
                self.dds.d2_2dv_c.off()
                self.dds.d2_2dv_r.off()

    @kernel
    def switch_d2_3d(self,state):
        if state == 1:
            with parallel:
                self.dds.d2_3d_c.on()
                self.dds.d2_3d_r.on()
        elif state == 0:
            with parallel:
                self.dds.d2_3d_c.off()
                self.dds.d2_3d_r.off()

    @kernel
    def switch_d1_3d(self,state,load_dac=True):
        if state == 1:
            self.dds.d1_3d_c.on(dac_load=False)
            self.dds.d1_3d_r.on(dac_load=False)
        elif state == 0:
            self.dds.d1_3d_c.off(dac_load=False)
            self.dds.d1_3d_r.off(dac_load=False)
        if load_dac:
            self.dac.load()

    @kernel
    def set_zshim_magnet_current(self, v = dv, load_dac=True):
        if v == dv:
            v = self.params.v_zshim_current
        with sequential:
            self.dac.zshim_current_control.set(v, load_dac)

    ## Other
    
    @kernel
    def mot_observe(self,
            detune_d2_c = dv,
            amp_d2_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            detune_push = dv,
            amp_push = dv,
            v_2d_mot_supply = dv,
            frequency_ry_405 = dv,
            amp_ry_405 = dv,
            frequency_ry_980 = dv,
            amp_ry_980 = dv,
            i_supply = dv,
            v_zshim_current = dv):
        
        ### Start Defaults ###
        if detune_d2_c == dv:
            detune_d2_c = self.params.detune_d2_c_mot
        if amp_d2_c == dv:
            amp_d2_c = self.params.amp_d2_c_mot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_mot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_mot
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if v_2d_mot_supply == dv:
            v_2d_mot_supply = self.params.v_2d_mot_current
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if frequency_ry_405 == dv:
            frequency_ry_405 = self.params.frequency_ao_ry_405_switch
        if amp_ry_405 == dv:
            amp_ry_405 = self.params.amp_ao_ry_405_switch
        if frequency_ry_980 == dv:
            frequency_ry_980 = self.params.frequency_ao_ry_980_switch
        if amp_ry_980 == dv:
            amp_ry_980 = self.params.amp_ao_ry_980_switch
        if i_supply == dv:
            i_supply = self.params.i_mot
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current
        ### End Defaults ###

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay(self.params.t_rtio)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay(self.params.t_rtio)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        delay(self.params.t_rtio)
        # self.dds.ry_980_switch.set_dds(frequency=frequency_ry_405,
        #                         amplitude=amp_ry_405)
        # delay(self.params.t_rtio)
        # self.dds.ry_405_switch.set_dds(frequency=frequency_ry_980,
        #                         amplitude=amp_ry_980)
        
        self.ttl.d2_mot_shutter.on()
        
        
        self.set_shims(v_zshim_current=v_zshim_current)

        delay(1*ms)

        # # return to mot load state
        self.dds.push.on()
        delay(1*ms)
        self.switch_d1_3d(0)
        delay(1*ms)
        self.switch_d2_3d(1)
        delay(1*ms)
        self.switch_d2_2d(1)

        self.dac.supply_current_2dmot.set(v=v_2d_mot_supply)

        # self.dds.ry_405_switch.on()
        # self.dds.ry_980_switch.on()

        self.dds.beatlock_ref.on()

        self.core.break_realtime()

        self.inner_coil.set_supply(i_supply)
        self.inner_coil.set_voltage(9.)
        self.inner_coil.on()

        self.outer_coil.off()

        self.dds.imaging.on()

    @kernel
    def set_shims(self,
                  v_xshim_current = dv,
                  v_yshim_current = dv,
                  v_zshim_current = dv):
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current

        self.dac.xshim_current_control.set(v = v_xshim_current)
        self.dac.yshim_current_control.set(v = v_yshim_current)
        self.dac.zshim_current_control.set(v = v_zshim_current)

    @kernel
    def power_down_cooling(self):
        """Turn off the near-resonant light for long hold times to avoid light
        leakage interacting with the atoms.
        """
        self.dds.d1_3d_r.set_dds(amplitude=0.)
        self.dds.d1_3d_c.set_dds(amplitude=0.)
        self.dds.d2_3d_c.set_dds(amplitude=0.)
        self.dds.d2_3d_r.set_dds(amplitude=0.)
        self.dds.d2_2dv_c.set_dds(amplitude=0.)
        self.dds.d2_2dv_r.set_dds(amplitude=0.)
        self.dds.d2_2dh_c.set_dds(amplitude=0.)
        self.dds.d2_2dh_r.set_dds(amplitude=0.)
        self.dds.push.set_dds(amplitude=0.)
        self.dds.mot_killer.set_dds(amplitude=0.)
        self.dds.optical_pumping.set_dds(amplitude=0.)
        self.dds.raman_minus.set_dds(amplitude=0.)
        self.dds.raman_plus.set_dds(amplitude=0.)
        # self.dds.imaging.set_dds(amplitude=0.)
        self.dds.antenna_rf.set_dds(amplitude=0.)

        # to avoid sequence errors from all the TTLs being at once
        self.dds.d1_3d_r.off()
        self.dds.d1_3d_c.off()
        self.dds.d2_3d_c.off()
        self.dds.d2_3d_r.off()
        self.dds.d2_2dv_c.off()
        self.dds.d2_2dv_r.off()
        self.dds.d2_2dh_c.off()
        self.dds.d2_2dh_r.off()
        delay_mu(8)
        self.dds.push.off()
        self.dds.mot_killer.off()
        self.dds.optical_pumping.off()
        self.dds.raman_minus.off()
        self.dds.raman_plus.off()
        # self.dds.imaging.off()
        self.dds.antenna_rf.off()
        delay_mu(8)

    @kernel
    def init_cooling(self):
        """See 'power_down_cooling`. Reboots the DDS cores for the near-resonant
        light and sets them to their defaults.
        """
        self.dds.d1_3d_r.set_dds(init=True)
        self.dds.d1_3d_c.set_dds(init=True)
        self.dds.d2_3d_c.set_dds(init=True)
        self.dds.d2_3d_r.set_dds(init=True)
        self.dds.d2_2dh_c.set_dds(init=True)
        self.dds.d2_2dh_r.set_dds(init=True)
        self.dds.d2_2dv_c.set_dds(init=True)
        self.dds.d2_2dv_r.set_dds(init=True)
        self.dds.push.set_dds(init=True)