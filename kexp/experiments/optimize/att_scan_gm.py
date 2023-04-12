from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
import numpy as np

class att_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.t_d2cmot = 5.e-3
        self.p.t_d1cmot = 7.e-3
        self.p.t_gm = 2e-3

        self.p.N_shots = 8
        # self.p.N_repeats = 1
        self.p.t_tof = 4000.e-6

        #MOT detunings
        self.p.detune_d2_c_mot = -3.3
        self.p.att_d2_c_mot = self.dds.d2_3d_c.att_dB
        self.p.detune_d2_r_mot = -4.7
        self.p.att_d2_r_mot = self.dds.d2_3d_r.att_dB

        #D2 CMOT detunings
        self.p.detune_d2_c_d2cmot = -.9
        self.p.att_d2_c_d2cmot = self.dds.d2_3d_c.att_dB
        self.p.detune_d2_r_d2cmot = -3.7
        self.p.att_d2_r_d2cmot = 12.5

        #D1 CMOT detunings
        self.p.detune_d1_c_d1cmot = 1.29
        self.p.att_d1_c_d1cmot = 11.5
        self.p.detune_d2_r_d1cmot = -3.7
        self.p.att_d2_r_d1cmot = self.p.att_d2_r_d2cmot
        
        #GM Detunings
        self.p.detune_d1_c_gm = 3.21
        self.p.att_d1_c_gm = np.linspace(2,6,self.p.N_shots)
        self.p.detune_d1_r_gm = 3.21
        self.p.att_d1_r_gm = np.linspace(11,30,self.p.N_shots)

        #MOT current settings
        self.p.V_d2cmot_current = 1.5
        self.p.V_d1cmot_current = .5

        self.xvarnames = ['att_d1_c_gm','att_d1_r_gm']

        self.get_N_img()

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t,att_c,att_r):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.p.detune_d1_c_gm, 
                                       att_dB=att_c)
        delay_mu(self.p.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=self.p.detune_d1_r_gm, 
                                       att_dB=att_r)
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

        for att_c in self.p.att_d1_c_gm:
            for att_r in self.p.att_d1_r_gm:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d2(self.p.t_d2cmot * s)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.gm(self.p.t_gm * s, att_c, att_r)
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
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

        

        


            

        

