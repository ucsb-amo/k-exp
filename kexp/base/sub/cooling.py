from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.expt_params import ExptParams
import numpy as np

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
                     detune_2d_c = 100.,
                     amp_2d_c = 100.,
                     detune_2d_r = 100.,
                     amp_2d_r = 100.):
        if detune_2d_c == 100.:
            detune_2d_c = self.params.detune_d2_c_2dmot
        if amp_2d_c == 100.:
            amp_2d_c = self.params.amp_d2_c_2dmot
        if detune_2d_r == 100.:
            detune_2d_r = self.params.detune_d2_r_2dmot
        if amp_2d_r == 100.:
            amp_2d_r = self.params.amp_d2_r_2dmot

        delay(-10*us)
        self.dds.d2_2d_c.set_dds_gamma(delta=detune_2d_c,
                                 amplitude=amp_2d_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_2d_r.set_dds_gamma(delta=detune_2d_r,
                                 amplitude=amp_2d_r)
        delay(10*us)
        with parallel:
            self.switch_d2_2d(1)
        delay(t)

    @kernel
    def mot(self,t):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=self.params.detune_d2_c_mot,
                                 amplitude=self.params.amp_d2_c_mot)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.params.detune_d2_r_mot,
                                 amplitude=self.params.amp_d2_r_mot)
        delay(10*us)
        self.set_magnet_current(V = self.params.V_mot_current)
        with parallel:
            self.ttl_magnets.on()
            self.switch_d2_3d(1)
            delay_mu(self.params.t_rtio_mu)
            self.dds.push.on()
        delay(t)

    @kernel
    def hybrid_mot(self,t):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=self.params.detune_d2_c_mot,
                                 amplitude=self.params.amp_d2_c_mot)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.params.detune_d2_r_mot,
                                 amplitude=self.params.amp_d2_r_mot)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_mot,
                                 amplitude=self.params.amp_d1_c_mot)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=self.params.detune_d1_r_mot,
                                 amplitude=self.params.amp_d1_r_mot)
        delay(10*us)
        self.set_magnet_current(V = self.params.V_mot_current)
        self.ttl_magnets.on()
        with parallel:
            self.switch_d2_3d(1)
            self.switch_d1_3d(1)
            self.dds.push.on()
        delay(t)

    #compress MOT by changing D2 detunings and raising B field
    @kernel
    def cmot_d2(self,t):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=self.params.detune_d2_c_d2cmot,
                                       amplitude=self.params.amp_d2_c_d2cmot)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.params.detune_d2_r_d2cmot,
                                       amplitude=self.params.amp_d2_r_d2cmot)
        delay(10*us)
        with parallel:
            self.switch_d2_3d(1)
            self.set_magnet_current(V = self.params.V_d2cmot_current)
        delay(t)

    #hybrid compressed MOT with only D2 repump and D1 cooler, setting B field to lower value
    @kernel
    def cmot_d1(self,t):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_d1cmot,
                                       amplitude=self.params.amp_d1_c_d1cmot)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.params.detune_d2_r_d1cmot,
                                       amplitude=self.params.amp_d2_r_d1cmot)
        delay(10*us)
        with parallel:
            self.dds.d2_3d_r.on()
            self.dds.d1_3d_c.on()
            self.dds.d2_3d_c.off()
            self.dds.d1_3d_r.off()
            self.set_magnet_current(V = self.params.V_d1cmot_current)
        delay(t)

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_gm, 
                                       amplitude=self.params.amp_d1_c_gm)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=self.params.detune_d1_r_gm, 
                                       amplitude=self.params.amp_d1_r_gm)
        delay(10*us)
        with parallel:
            self.ttl_magnets.off()
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)
        delay(t)

    #GM with only D1, turning B field off
    @kernel
    def gm_ramp(self,t,amp_c_list,amp_r_list):
        delay(-10*us)
        self.dds.d1_3d_r.set_dds_gamma(delta=self.params.detune_d1_r_gm, 
                                       amplitude=self.params.amp_d1_r_gm)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_gm, 
                                       amplitude=self.params.amp_d1_c_gm)
        delay(10*us)
        with parallel:
            self.ttl_magnets.off()
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)

        N = len(amp_c_list)
        dt = t / N
        for i in range(N):
            self.dds.d1_3d_c.set_dds(amp_c_list[i])
            self.dds.d1_3d_r.set_dds(amp_r_list[i])
            delay(dt - self.dds.d1_3d_c._t_set_delay_mu * 1.e-9 * 2)

    @kernel
    def release(self):
        with parallel:
            self.ttl_magnets.off()
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
            with parallel:
                self.dds.d1_3d_c.on()
                self.dds.d1_3d_r.on()
        elif state == 0:
            with parallel:
                self.dds.d1_3d_c.off()
                self.dds.d1_3d_r.off()

    ## Magnet functions

    @kernel
    def set_magnet_current(self, V = -0.1):
        if V < 0.:
            V = self.params.V_mot_current
        with sequential:
            self.zotino.write_dac(self.dac_ch_3Dmot_current_control,V)
            self.zotino.load()

    ## Other
    
    @kernel
    def mot_observe(self):
        # return to mot load state
        self.dds.push.on()
        delay(1*ms)
        self.switch_d1_3d(0)
        delay(1*ms)
        self.switch_d2_3d(1)
        delay(1*ms)
        self.switch_d2_2d(1)
        self.dds.imaging.off()

        self.core.break_realtime()
        self.set_magnet_current()
        self.ttl_magnets.on()