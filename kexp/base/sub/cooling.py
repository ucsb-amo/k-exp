from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.control.misc.big_coil import igbt_magnet, hbridge_magnet
from kexp.control.misc.awg_tweezer import tweezer
from kexp.control.misc.painted_lightsheet import lightsheet
from kexp.config.expt_params import ExptParams
import numpy as np

from kexp.util.artiq.async_print import aprint

dv = 100.
dvlist = np.linspace(1.,1.,5)

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
    def pump_to_F1(self):
        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                        v_xshim_current=self.p.v_xshim_current_magtrap)
        delay(2.e-3)
        self.dds.optical_pumping.set_dds(set_stored=True)
        self.dds.optical_pumping.on()
        delay(200.e-6)
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
                     detune_d2_c = dv,
                     amp_d2_c = dv,
                     detune_d2_r = dv,
                     amp_d2_r = dv,
                     detune_push = dv,
                     amp_push = dv,
                     i_supply = dv):
        
        ### Start Defaults ###
        if detune_d2_c == dv:
            detune_d2_c = self.params.detune_d2_c_2dmot
        if amp_d2_c == dv:
            amp_d2_c = self.params.amp_d2_c_2dmot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_2dmot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_2dmot
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if i_supply == dv:
            i_supply = self.params.v_2d_mot_current
        ### End Defaults ###

        self.dds.d2_2d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay(self.params.t_rtio)
        self.dds.d2_2d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay(self.params.t_rtio)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        
        self.dac.supply_current_2dmot.set(v=i_supply)

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
            
        self.inner_coil.set_current(i_supply)
        self.inner_coil.set_voltage(i_supply)
        self.inner_coil.on()

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay(self.params.t_rtio)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay(self.params.t_rtio)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
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
            
        self.inner_coil.set_current(i_supply)
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

        self.inner_coil.set_current(i_supply)
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
            
        self.inner_coil.set_current(i_supply)
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
            i_supply = self.params.i_mot
        ### End Defaults ###
            
        # self.inner_coil.set_current(i_supply)
        self.inner_coil.set_current(self.params.i_magtrap_init)
        self.inner_coil.set_voltage(i_supply)
        self.inner_coil.on()

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
            detune_d1_c_list = dvlist,
            v_pd_d1_c = dv,
            amp_d1_c = dv,
            detune_d2_r_list = dvlist,
            amp_d2_r = dv,
            i_supply = dv):
        
        ### Start Defaults ###
        if detune_d1_c_list == dvlist:
            detune_d1_c_list = self.params.detune_d1_c_list_d1cmot
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_d1cmot
        if amp_d1_c == dv:
            amp_d1_c = self.params.amp_d1_3d_c
        if detune_d2_r_list == dvlist:
            detune_d2_r_list = self.params.detune_d2_r_list_d1cmot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_d1cmot
        if i_supply == dv:
            i_supply = self.params.i_cmot
        ### End Defaults ###
            
        dt = t / self.params.n_d1cmot_detuning_sweep_steps
        self.inner_coil.set_current(i_supply)
        self.inner_coil.set_voltage(i_supply)
        self.inner_coil.on()

        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c_list[0],
                                       v_pd=v_pd_d1_c)
        delay(self.params.t_rtio)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r_list[0],
                                       amplitude=amp_d2_r)

        # with parallel:
        self.dds.d2_3d_r.on()
        self.dds.d1_3d_c.on()
        delay(self.params.t_rtio)
        self.dds.d2_3d_c.off()
        self.dds.d1_3d_r.off()

        for i in range(self.params.n_d1cmot_detuning_sweep_steps):
            self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c_list[i])
            self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r_list[i])
            delay(dt)
        
        delay(t)

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

    # @kernel
    # def gm_ramp(self,t,t_ramp,
    #         detune_d1_c = dv,
    #         v_pd_d1_c = dv,
    #         detune_d1_r = dv,
    #         v_pd_d1_r = dv,
    #         detune_d1 = dv,
    #         dds_mgr_idx = 0):
        
    #     ### Start Defaults ###
    #     if detune_d1 != dv:
    #         detune_d1_c = detune_d1
    #         detune_d1_r = detune_d1
    #     else:
    #         if detune_d1_c == dv:
    #             detune_d1_c = self.params.detune_d1_c_gm
    #         if detune_d1_r == dv:
    #             detune_d1_r = self.params.detune_d1_r_gm
        
    #     if v_pd_d1_c == dv:
    #         v_pd_d1_c = self.params.v_pd_d1_c_gm
    #     if v_pd_d1_r == dv:
    #         v_pd_d1_r = self.params.v_pd_d1_r_gm
    #     ### End Defaults ###

    #     self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c, 
    #                                    v_pd=v_pd_d1_c)
    #     delay(self.params.t_rtio)
    #     self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
    #                                    v_pd=v_pd_d1_r)
        
    #     self.dds.load_profile(dds_mgr_idx)

    #     with parallel:
    #         self.ttl.inner_coil_igbt.off()
    #         self.switch_d1_3d(1)
    #         self.switch_d2_3d(0)
    #     delay(t)
    #     self.dds.enable_profile(dds_mgr_idx)
    #     delay(t_ramp)
    #     # delay(t)
    #     self.dds.disable_profile(dds_mgr_idx)

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
    def start_magtrap(self,
                        v_zshim_current=dv,
                        v_yshim_current=dv,
                        v_xshim_current=dv):
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current_magtrap
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current_magtrap
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current_magtrap
        
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.pump_to_F1()

        self.dds.power_down_cooling()
        

        self.set_shims(v_zshim_current=v_zshim_current,
                        v_yshim_current=v_yshim_current,
                        v_xshim_current=v_xshim_current)

        # magtrap start
        self.inner_coil.on()

    @kernel
    def magtrap_and_load_lightsheet(self,
                                t_lightsheet_ramp=dv,
                                t_magtrap_ramp=dv,
                                t_magtrap_rampdown=dv,
                                v_pd_lightsheet_ramp_start=dv,
                                v_pd_lightsheet_ramp_end=dv,
                                paint_lightsheet=False,
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

        # ramp up lightsheet over magtrap
        

        self.lightsheet.ramp(t_lightsheet_ramp,
                            v_pd_lightsheet_ramp_start,
                            v_pd_lightsheet_ramp_end,
                            paint=paint_lightsheet,
                            v_awg_am_max=v_awg_paint_amp_lightsheet,
                            keep_trap_frequency_constant=False)

        self.inner_coil.ramp(t=t_magtrap_ramp,
                            i_start=i_magtrap_init,
                            i_end=i_magtrap_ramp_end)
        
        delay(self.params.t_magtrap)

        self.inner_coil.ramp(t=t_magtrap_rampdown,
                            i_start=i_magtrap_ramp_end,
                            i_end=0.)
        self.inner_coil.off()

    @kernel
    def magtrap(self,
                t_magtrap_ramp=dv,
                i_magtrap_init=dv,
                i_magtrap_ramp_end=dv,
                v_zshim_current=dv,
                v_yshim_current=dv,
                v_xshim_current=dv):
        if t_magtrap_ramp == dv:
            t_magtrap_ramp = self.params.t_magtrap_ramp
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

        self.inner_coil.ramp(t=t_magtrap_ramp,
                            i_start=i_magtrap_init,
                            i_end=i_magtrap_ramp_end)


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
                self.dds.d2_2d_c.on()
                self.dds.d2_2d_r.on()
        elif state == 0:
            with parallel:
                self.dds.d2_2d_c.off()
                self.dds.d2_2d_r.off()

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
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if frequency_ry_405 == dv:
            frequency_ry_405 = self.params.frequency_ao_ry_405
        if amp_ry_405 == dv:
            amp_ry_405 = self.params.amp_ao_ry_405
        if frequency_ry_980 == dv:
            frequency_ry_980 = self.params.frequency_ao_ry_980
        if amp_ry_980 == dv:
            amp_ry_980 = self.params.amp_ao_ry_980
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
        self.dds.ry_980.set_dds(frequency=frequency_ry_405,
                                amplitude=amp_ry_405)
        delay(self.params.t_rtio)
        self.dds.ry_405.set_dds(frequency=frequency_ry_980,
                                amplitude=amp_ry_980)
        
        
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

        self.dds.ry_405.on()
        self.dds.ry_980.on()

        self.dds.beatlock_ref.on()

        self.core.break_realtime()

        self.inner_coil.set_current(i_supply)
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