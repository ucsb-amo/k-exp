from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
import numpy as np

class detune_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "detune vs amp scan gm, two-photon detuning = 0"

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.t_d2cmot = 5.e-3
        self.t_d1cmot = 7.e-3
        self.p.t_gm = 2.e-3

        self.p.t_tof = 2.e-3

        #MOT detunings

        # scan_center = 4.8

        self.p.detune_d1_gm = np.linspace(4.5,6.5,7)
        self.p.detune_d1_c_gm = self.p.detune_d1_gm
        self.p.detune_d1_r_gm = self.p.detune_d1_gm

        self.p.amp_d1_gm = np.linspace(0.09,0.12,7)
        self.p.amp_d1_c_gm = self.p.amp_d1_gm
        self.p.amp_d1_r_gm = self.p.amp_d1_gm

        self.xvarnames = ['detune_d1_gm','amp_d1_gm']

        self.get_N_img()

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t,delta,amp):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=delta, 
                                       amplitude=amp)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d1_3d_r.set_dds_gamma(delta=delta, 
                                       amplitude=amp)
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

        for delta in self.p.detune_d1_gm:
            for amp in self.p.amp_d1_gm:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d2(self.p.t_d2cmot)
                self.cmot_d1(self.p.t_d1cmot)

                self.gm(self.p.t_gm, delta, amp)
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")

        

        


            

        

