from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.analysis.base_analysis import atomdata
from kexp.base.base import Base
import numpy as np

class tof_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.t_d2_cmot = 5.e-3
        self.p.t_hybrid_cmot = 7.e-3
        self.p.t_gm = 1.5e-3

        self.p.N_shots = 5
        self.p.N_repeats = 1
        self.p.t_tof = np.linspace(1000,3000,self.p.N_shots) * 1.e-6
        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        #MOT detunings

        self.p.detune_d2_c_mot = -3.3
        self.p.att_d2_c_mot = self.dds.d2_3d_c.att_dB
        self.p.detune_d2_r_mot = -4.7
        self.p.att_d2_r_mot = self.dds.d2_3d_r.att_dB

        #CMOT detunings
        self.p.detune_d2_c_cmot = -.9
        self.p.att_d2_c_cmot = self.dds.d2_3d_c.att_dB
        self.p.detune_d2_r_cmot = -3.7
        self.p.att_d2_r_cmot = 12.5

        self.p.detune_d1_c_cmot = 3.5

        #GM Detunings
        # self.p.delta_gm_r = np.linspace(0.0,4.5,8)
        self.p.detune_d1_c_gm = 1.29
        self.p.att_d1_c_gm = self.dds.d1_3d_c.att_dB
        self.p.detune_d1_r_gm = np.linspace(0.0,4.5,8)
        self.p.att_d1_r_gm = self.dds.d1_3d_r.att_dB

        #MOT current settings
        self.p.V_cmot0_current = 1.5
        self.p.V_cmot_current = .4

        self.xvarnames = ['detune_d1_r_gm','t_tof']

        self.get_N_img()

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t,delta):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.p.detune_d1_c_gm, 
                                       att_dB=self.p.att_d1_c_gm)
        delay_mu(self.p.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=delta, 
                                       att_dB=self.p.att_d1_r_gm)
        delay(10*us)
        with parallel:
            self.switch_mot_magnet(0)
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)
        delay(t)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for delta in self.p.detune_d1_r_gm:
            for t_tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d2(self.p.t_d2_cmot * s)

                # self.cmot(self.p.t_hybrid_cmot * s)

                self.gm(self.p.t_gm * s, delta)
                
                self.release()
                
                ### abs img
                delay(t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.switch_all_dds(state=1)
        self.dds.imaging.off()
        self.core.break_realtime()
        self.switch_mot_magnet(1)

        self.zotino.write_dac(self.dac_ch_3Dmot_current_control,0.7)
        self.zotino.load()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")

        

        


            

        

