from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
import numpy as np

class test_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.t_d2_cmot = 5.e-3
        self.p.t_hybrid_cmot = 7.e-3
        self.p.t_gm = 1.5e-3

        self.p.N_repeats = 1

        self.p.t_tof = np.linspace(100.,1500.,3) * 1.e-6

        #MOT detunings

        self.p.amp_d2_mot = np.linspace(0,0.188,2)

        self.xvarnames = ['amp_d2_mot','t_tof']

        self.get_N_img()

    @kernel
    def mot(self,t,amp):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=self.p.detune_d2_c_mot, amplitude=amp)
        delay_mu(self.p.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=self.p.detune_d2_r_mot, amplitude=amp)
        delay(10*us)
        with parallel:
            self.switch_mot_magnet(1)
            self.switch_d2_3d(1)
            delay_mu(self.p.t_rtio_mu)
            self.dds.push.on()
        delay(t)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for amp in self.p.amp_d2_mot:
            for t_tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s, amp)

                self.dds.push.off()
                self.switch_d2_2d(0)
                
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

        

        


            

        

