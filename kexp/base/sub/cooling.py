from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.expt_params import ExptParams
import numpy as np

from kexp.util.artiq.async_print import aprint

dv = 100.

class Cooling():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        # just to get syntax highlighting

    ## cooling stages

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.push.off()
            self.switch_d2_3d(0)
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

        delay(-10*us)
        self.dds.d2_2d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_2d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        delay(10*us)
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
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if v_current == dv:
            v_current = self.params.v_mot_current
        ### End Defaults ###

        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        delay(10*us)
        self.set_magnet_current(v = v_current)
        with parallel:
            self.ttl_magnets.on()
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
        if v_current == dv:
            v_current = self.params.v_mot_current
        ### End Defaults ###

        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay(10*us)
        self.set_magnet_current(v = v_current)
        with parallel:
            self.ttl_magnets.on()
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

        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                 v_pd=v_pd_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r,
                                 amplitude=v_pd_r)
        delay(10*us)
        self.set_magnet_current(v = v_current)
        self.ttl_magnets.on()
        with parallel:
            self.switch_d2_3d(1)
            self.switch_d1_3d(1)
            self.dds.push.on()
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

        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                       amplitude=amp_d2_c)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                       amplitude=amp_d2_r)
        delay(10*us)
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

        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                       v_pd=v_pd_d1_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                       amplitude=amp_d2_r)
        delay(10*us)

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

        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c, 
                                       v_pd=v_pd_d1_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
                                       v_pd=v_pd_d1_r)
        delay(10*us)
        with parallel:
            self.ttl_magnets.off()
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)
        delay(t)

    #GM with only D1, turning B field off
    @kernel
    def gm_tweezer(self,t,
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

        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c, 
                                       v_pd=v_pd_d1_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=detune_d1_r, 
                                       v_pd=v_pd_d1_r)
        delay(10*us)
        with parallel:
            self.ttl_magnets.off()
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)
        self.dds.tweezer.on()
        delay(t)

    @kernel
    def release(self):
        with parallel:
            self.ttl_magnets.off()
            self.switch_d2_3d(0)
            self.switch_d1_3d(0)

    #switch on a single 1227 trap for time t
    @kernel
    def tweezer_trap(self,t,
                     frequency_ao_1227 = dv,
                     amp_1227 = dv):
        
        if frequency_ao_1227 == dv:
            frequency_ao_1227 = self.params.frequency_ao_1227
        if amp_1227 == dv:
            amp_1227 = self.params.amp_1227

        delay(-10*us)
        self.dds.tweezer.set_dds(frequency=frequency_ao_1227,
                                       amplitude=amp_1227)
        delay(10*us)
        self.dds.tweezer.on()
        delay(t)

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
            self.zotino.load()
        elif state == 0:
            self.dds.d1_3d_c.off(dac_load=False)
            self.dds.d1_3d_r.off(dac_load=False)
            self.zotino.load()

    ## Magnet functions

    @kernel
    def set_magnet_current(self, v = dv):
        if v == dv:
            v = self.params.v_mot_current
        with sequential:
            self.zotino.write_dac(self.dac_ch_3Dmot_current_control,v)
            self.zotino.load()

    ## Other
    
    @kernel
    def mot_observe(self,
            detune_d2_c = dv,
            amp_d2_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv,
            detune_push = dv,
            amp_push = dv,
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
        if detune_push == dv:
            detune_push = self.params.detune_push
        if amp_push == dv:
            amp_push = self.params.amp_push
        if v_current == dv:
            v_current = self.params.v_mot_current
        ### End Defaults ###

        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=detune_d2_c,
                                 amplitude=amp_d2_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                 amplitude=amp_d2_r)
        delay_mu(self.params.t_rtio_mu)
        self.dds.push.set_dds_gamma(delta=detune_push,
                                 amplitude=amp_push)
        delay(10*us)
        self.dds.imaging_4_real.set_dds_gamma(delta=5.,
                                 amplitude=.188)
        delay(10*us)
        self.set_magnet_current(v = v_current)

        delay(1*ms)

        # return to mot load state
        self.dds.push.on()
        delay(1*ms)
        self.switch_d1_3d(0)
        delay(1*ms)
        self.switch_d2_3d(1)
        delay(1*ms)
        self.switch_d2_2d(1)
        self.dds.imaging.off()

        self.dds.tweezer.on()

        self.dds.imaging_4_real.on()

        self.core.break_realtime()
        self.set_magnet_current()
        self.ttl_magnets.on()