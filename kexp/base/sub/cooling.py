from artiq.experiment import *
from artiq.experiment import delay, delay_mu, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.expt_params import ExptParams

class cooling():
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
    def mot_2d(self,t):
        with parallel:
            self.switch_d2_2d(1)
        delay(t)

    @kernel
    def mot(self,t):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=self.p.detune_d2_c_mot,
                                 att_dB=self.p.att_d2_c_mot)
        delay_mu(self.p.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.p.detune_d2_r_mot,
                                 att_dB=self.p.att_d2_r_mot)
        delay(10*us)
        with parallel:
            self.switch_mot_magnet(1)
            self.switch_d2_3d(1)
            delay_mu(self.p.t_rtio_mu)
            self.dds.push.on()
        delay(t)

    #compress MOT by changing D2 detunings and raising B field
    @kernel
    def cmot_d2(self,t):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=self.p.detune_d2_c_d2cmot,
                                       att_dB=self.p.att_d2_c_d2cmot)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.p.detune_d2_r_d2cmot,
                                       att_dB=self.p.att_d2_r_d2cmot)
        delay(10*us)
        with parallel:
            self.switch_d2_3d(1)
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                      self.p.V_d2cmot_current)
                self.zotino.load()
        delay(t)

    #hybrid compressed MOT with only D2 repump and D1 cooler, setting B field to lower value
    @kernel
    def cmot_d1(self,t):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.p.detune_d1_c_d1cmot,
                                       att_dB=self.p.att_d2_r_d1cmot)
        delay_mu(self.p.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.p.detune_d2_r_d1cmot,
                                       att_dB=self.p.att_d2_r_d1cmot)
        delay(10*us)
        with parallel:
            self.dds.d2_3d_r.on()
            self.dds.d1_3d_c.on()
            self.dds.d2_3d_c.off()
            self.dds.d1_3d_r.off()
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                      self.p.V_d1cmot_current)
                self.zotino.load()
        delay(t)

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t):
        delay(-10*us)
        self.dds.d1_3d_r.set_dds_gamma(delta=self.p.detune_d1_r_gm, 
                                       att_dB=self.p.att_d1_r_gm)
        delay_mu(self.p.t_rtio_mu)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.p.detune_d1_c_gm, 
                                       att_dB=self.p.att_d1_c_gm)
        delay(10*us)
        with parallel:
            self.switch_mot_magnet(0)
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)
        delay(t)

    @kernel
    def release(self):
        with parallel:
            self.switch_mot_magnet(0)
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
    def switch_mot_magnet(self, state = 0):
        if state == 1:
            V = self.params.V_mot_current
        else:
            V = 0.
        with sequential:
            self.zotino.write_dac(self.dac_ch_3Dmot_current_control,V)
            self.zotino.load()