from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams
import numpy as np

from kexp.util.artiq.async_print import aprint

dv = 100.
dvlist = np.linspace(1.,1.,5)

class Cooling():
    def __init__(self):
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.dac = dac_frame()
        self.params = ExptParams()
        # just to get syntax highlighting

    ## cooling stages

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.push.off()
            self.switch_d2_3d(0)
            self.set_magnet_current(0.)
        delay(t)

    @kernel
    def load_2D_mot(self, t,
                     detune_d2_c = dv,
                     amp_d2_c = dv,
                     detune_d2_r = dv,
                     amp_d2_r = dv,
                     detune_push = dv,
                     amp_push = dv):
        
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
        ### End Defaults ###

        self.dds.d2_2d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_2d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
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
            v_current = dv,
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
        if v_current == dv:
            v_current = self.params.v_mot_current
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current
        if v_yshim_current == dv:
            v_yshim_current = self.params.v_yshim_current
        if v_xshim_current == dv:
            v_xshim_current = self.params.v_xshim_current
        ### End Defaults ###

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        self.set_magnet_current(v = v_current)
        self.set_zshim_magnet_current(v = v_zshim_current)
        self.dac.xshim_current_control.set(v = v_xshim_current)
        self.dac.yshim_current_control.set(v = v_yshim_current)
        with parallel:
            self.ttl.magnets.on()
            self.switch_d2_3d(1)
            # delay_mu(self.params.t_rtio_mu)
            self.dds.push.on()
        delay(t)

    @kernel
    def mot_reload(self,t,
            detune_d2_c = dv,
            amp_d2_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            v_current = dv,
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
        if v_current == dv:
            v_current = self.params.v_mot_current
        if v_zshim_current == dv:
            v_current = self.params.v_zshim_current
        ### End Defaults ###

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        self.set_magnet_current(v = v_current)
        self.set_zshim_magnet_current(v=v_zshim_current)
        with parallel:
            self.ttl.magnets.on()
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
            v_current = dv):
        
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

        if v_current == dv:
            v_current = self.params.v_mot_current

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                 v_pd=v_pd_d1_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r,
                                 amplitude=v_pd_d1_r)
        self.set_magnet_current(v = v_current)
        self.ttl.magnets.on()
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
            v_current = dv):
        
        ### Start Defaults ###
        if detune_d2_c == dv:
            detune_d2_c = self.params.detune_d2_c_d2cmot
        if amp_d2_c == dv:
            amp_d2_c = self.params.amp_d2_c_d2cmot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_d2cmot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_d2cmot
        if v_current == dv:
            v_current = self.params.v_d2cmot_current
        ### End Defaults ###

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                       amplitude=amp_d2_c)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                       amplitude=amp_d2_r)
        with parallel:
            self.switch_d2_3d(1)
            self.set_magnet_current(v = v_current)
        delay(t)

    #hybrid compressed MOT with only D2 repump and D1 cooler, setting B field to lower value
    @kernel
    def cmot_d1(self,t,
            detune_d1_c = dv,
            v_pd_d1_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            v_current = dv):
        
        ### Start Defaults ###
        if detune_d1_c == dv:
            detune_d1_c = self.params.detune_d1_c_d1cmot
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_d1cmot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_d1cmot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_d1cmot
        if v_current == dv:
            v_current = self.params.v_d1cmot_current
        ### End Defaults ###

        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                       v_pd=v_pd_d1_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                       amplitude=amp_d2_r)

        # with parallel:
        self.dds.d2_3d_r.on()
        self.dds.d1_3d_c.on()
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_c.off()
        self.dds.d1_3d_r.off()
        self.set_magnet_current(v = v_current)
        delay(t)

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t,
            detune_d1_c = dv,
            v_pd_d1_c = dv,
            detune_d1_r = dv,
            v_pd_d1_r = dv,
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
        
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_gm
        if v_pd_d1_r == dv:
            v_pd_d1_r = self.params.v_pd_d1_r_gm
        ### End Defaults ###

        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c, 
                                       v_pd=v_pd_d1_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
                                       v_pd=v_pd_d1_r)
        with parallel:
            self.ttl.magnets.off()
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
    #     delay_mu(self.params.t_rtio_mu)
    #     self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
    #                                    v_pd=v_pd_d1_r)
        
    #     self.dds.load_profile(dds_mgr_idx)

    #     with parallel:
    #         self.ttl.magnets.off()
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
            detune_d1_r = dv,
            v_pd_d1_r_list = dvlist,
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
                                       v_pd=v_pd_d1_c_list[0])
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
                                       v_pd=v_pd_d1_r_list[0])

        self.switch_d1_3d(1)

        for n in range(N_elem):
            self.dds.d1_3d_c.set_dds(v_pd=v_pd_d1_c_list[n])
            delay_mu(self.params.t_rtio_mu)
            self.dds.d1_3d_r.set_dds(v_pd=v_pd_d1_r_list[n])
            delay(dt_gmramp)

    @kernel
    def optical_pumping(self, t,
                        t_bias_rampup=dv,
                        detune_optical_pumping=dv,
                        amp_optical_pumping=dv,
                        v_zshim_current=dv,
                        detune_optical_pumping_r=dv,
                        amp_optical_pumping_r=dv):
        
        if t_bias_rampup == dv:
            t_bias_rampup = self.params.t_optical_pumping_bias_rampup
        if detune_optical_pumping == dv:
            detune_optical_pumping = self.params.detune_optical_pumping_op
        if amp_optical_pumping == dv:
            amp_optical_pumping = self.params.amp_optical_pumping_op
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current_op
        if detune_optical_pumping_r == dv:
            detune_optical_pumping_r = self.params.detune_optical_pumping_r_op
        if amp_optical_pumping_r == dv:
            amp_optical_pumping_r = self.params.amp_optical_pumping_r_op

        self.set_zshim_magnet_current(v_zshim_current)
        self.dds.optical_pumping.set_dds_gamma(delta=detune_optical_pumping, 
                                       amplitude=amp_optical_pumping)
        self.dds.op_r.set_dds_gamma(delta=detune_optical_pumping_r,
                              amplitude=amp_optical_pumping_r)
        delay(t_bias_rampup)
        if t:
            self.dds.optical_pumping.on()
            self.dds.op_r.on()
            delay(t)
            self.dds.optical_pumping.off()
            self.dds.op_r.off()
        self.set_zshim_magnet_current(self.params.v_zshim_current)
        
    @kernel
    def tweezer_ramp(self, t_tweezer_ramp = dv,
            v_pd_tweezer_ramp_list = dvlist):
        
        ### Start Defaults ###
        
        if v_pd_tweezer_ramp_list == dvlist:
            v_pd_tweezer_ramp_list = self.params.v_pd_tweezer_ramp_list

        # check for list length agreement
        N_elem = len(v_pd_tweezer_ramp_list)
        
        if t_tweezer_ramp == dv:
            t_tweezer_ramp = self.params.t_tweezer_ramp
            dt_tweezer_ramp = self.params.dt_tweezer_ramp
        else:
            dt_tweezer_ramp = t_tweezer_ramp / N_elem

        ### End Defaults ###

        self.dds.tweezer.set_dds(frequency=self.params.frequency_ao_1227,
                                 v_pd=v_pd_tweezer_ramp_list[0])
        self.dds.tweezer.on()
        for n in range(N_elem):
            self.dds.tweezer.set_dds(v_pd=v_pd_tweezer_ramp_list[n])
            delay(dt_tweezer_ramp)

    @kernel
    def release(self):
        with parallel:
            self.ttl.magnets.off()
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
    def switch_d1_3d(self,state):
        if state == 1:
            self.dds.d1_3d_c.on(dac_load=False)
            self.dds.d1_3d_r.on(dac_load=False)
            self.dac.load()
        elif state == 0:
            self.dds.d1_3d_c.off(dac_load=False)
            self.dds.d1_3d_r.off(dac_load=False)
            self.dac.load()

    ## Magnet functions

    @kernel
    def set_magnet_current(self, v = dv):
        if v == dv:
            v = self.params.v_mot_current
        with sequential:
            self.dac.mot_current_control.set(v)

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
            v_current = dv,
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
        if v_current == dv:
            v_current = self.params.v_mot_current
        if v_zshim_current == dv:
            v_zshim_current = self.params.v_zshim_current
        ### End Defaults ###

        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        
        self.set_magnet_current(v = v_current)
        self.set_zshim_magnet_current(v = v_zshim_current)

        delay(1*ms)

        # return to mot load state
        self.dds.push.on()
        delay(1*ms)
        self.switch_d1_3d(0)
        delay(1*ms)
        self.switch_d2_3d(1)
        delay(1*ms)
        self.switch_d2_2d(1)

        self.dds.beatlock_ref.on()

        self.core.break_realtime()
        self.ttl.magnets.on()

        self.dds.imaging.on()