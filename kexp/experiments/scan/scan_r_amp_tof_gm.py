from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.config import power_fraction_to_dds_amplitude
from kexp import Base

import numpy as np

class scan_r_amp_tof_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.t_d2cmot = 5.e-3
        self.p.t_d1cmot = 7.e-3
        self.p.t_gm = 2.e-3
        
        self.p.N_repeats = 2

        self.p.t_tof = np.linspace(2000,5000,5) * 1.e-6
        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        self.p.detune_gm = 8
        self.p.detune_d1_c_gm = self.p.detune_gm
        self.p.detune_d1_r_gm = self.p.detune_gm

        self.p.amp_d1_r_gm = power_fraction_to_dds_amplitude(np.linspace(1.,0.01,10))

        self.xvarnames = ['amp_d1_r_gm','t_tof']

        self.get_N_img()
        
    @kernel
    def gm(self,t,amp_r):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_gm, 
                                       amplitude=self.params.amp_d1_c_gm)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=self.params.detune_d1_r_gm, 
                                       amplitude=amp_r)
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
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for amp_r in self.p.amp_d1_r_gm:
            for t_tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d2(self.p.t_d2cmot * s)
                self.cmot_d1(self.p.t_d1cmot * s)

                self.gm(self.p.t_gm * s, amp_r)
                
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

        self.zotino.write_dac(self.dac_ch_3Dmot_current_control,self.p.V_mot_current)
        self.zotino.load()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")