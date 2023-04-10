from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.analysis.base_analysis import atomdata
from kexp.base.base import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.t_d2cmot = 5.e-3
        self.p.t_d1cmot = 7.e-3
        self.p.t_gm = 7.e-3

        self.p.N_shots = 5
        self.p.N_repeats = 1
        self.p.t_tof = np.linspace(2000,4000,self.p.N_shots) * 1.e-6
        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        #MOT detunings

        self.p.detune_d2_c_mot = -3.3
        self.p.att_d2_c_mot = self.dds.d2_3d_c.att_dB
        self.p.detune_d2_r_mot = -4.7
        self.p.att_d2_r_mot = self.dds.d2_3d_r.att_dB

        #CMOT detunings
        self.detune_d2_c_d2cmot = -.9
        self.att_d2_c_d2cmot = self.dds.d2_3d_c.att_dB
        self.detune_d2_r_d2cmot = -3.7
        self.att_d2_r_d2cmot = 12.5

        self.p.detune_d1_c_d1cmot = 1.29
        self.p.att_d1_c_d1cmot = 11.5
        self.p.detune_d2_r_d1cmot = -3.7
        self.p.att_d2_r_d1cmot = self.p.att_d2_r_d2cmot

        #GM Detunings
        self.p.detune_d1_c_gm = 1.29
        self.p.att_d1_c_gm = 11.5
        self.p.detune_d1_r_gm = 3.21
        self.p.att_d1_r_gm = 11.0

        #MOT current settings
        self.p.V_d2cmot_current = 1.5
        self.p.V_d1cmot_current = .5

        self.xvarnames = ['t_tof']

        self.get_N_img()
    
    @kernel
    def load_2D_mot(self,t):
        with parallel:
            self.switch_d2_2d(1)
        delay(t)

    @kernel
    def load_mot(self,t):
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

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.push.off()
            self.switch_d2_3d(0)
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
    def kill_trap(self):
        with parallel:
            self.switch_mot_magnet(0)
            self.switch_d2_3d(0)
            self.switch_d1_3d(0)

    @kernel
    def abs_image(self):
        self.trigger_camera()
        self.pulse_imaging_light(self.p.t_imaging_pulse * s)

        delay(self.p.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.p.t_imaging_pulse * s)

        self.dds.imaging.off()
        delay(self.p.t_dark_image_delay * s)
        self.trigger_camera()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t_tof in self.p.t_tof:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.load_mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d2(self.p.t_d2cmot * s)

            self.cmot_d1(self.p.t_d1cmot * s)

            self.gm(self.p.t_gm * s)
            
            self.kill_trap()
            
            ### abs img
            delay(t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        # return to mot load state
        self.switch_all_dds(state=1)

        self.dds.d1_3d_c.off()
        self.dds.d1_3d_r.off()
        self.dds.d2_3d_c.set_dds_gamma(delta=self.p.detune_d2_c_mot,
                                        att_dB=self.p.att_d2_c_mot)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.p.detune_d2_r_mot,
                                        att_dB=self.p.att_d2_r_mot)
        self.dds.imaging.off()

        self.core.break_realtime()
        self.switch_mot_magnet(1)

        self.zotino.write_dac(self.dac_ch_3Dmot_current_control,0.7)
        self.zotino.load()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")

        

        


            

        

