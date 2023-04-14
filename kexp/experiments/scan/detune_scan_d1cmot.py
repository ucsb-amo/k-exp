from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
import numpy as np

class detune_scan_d1cmot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.t_d2cmot = 5.e-3
        self.t_d1cmot = 1.e-3
        self.p.t_gm = 1.5e-3

        # self.p.N_shots = 4
        self.p.N_repeats = 1

        self.p.t_tof = 2500.e-6

        #MOT detunings

        self.p.detune_d1_c_d1cmot = np.linspace(0,8.5,10)
        self.p.detune_d2_r_d1cmot = np.linspace(-3,-4.5,7)

        self.xvarnames = ['detune_d1_c_d1cmot','detune_d2_r_d1cmot']

        self.get_N_img()

    @kernel
    def cmot_d1(self,t,delta_d1c,delta_d2r):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=delta_d1c,
                                       amplitude=self.params.amp_d1_c_d1cmot)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=delta_d2r,
                                       amplitude=self.params.amp_d2_r_d1cmot)
        delay(10*us)
        with parallel:
            self.dds.d2_3d_r.on()
            self.dds.d1_3d_c.on()
            self.dds.d2_3d_c.off()
            self.dds.d1_3d_r.off()
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                      self.params.V_d1cmot_current)
                self.zotino.load()
        delay(t)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for delta_d1c in self.p.detune_d1_c_d1cmot:
            for delta_d2r in self.p.detune_d2_r_d1cmot:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d2(self.p.t_d2cmot)
                self.cmot_d1(self.p.t_d1cmot, delta_d1c, delta_d2r)
                
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

        

        


            

        

