from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
import numpy as np

class detune_vs_amp_d1cmot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "d1 cmot detune vs field"

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        # self.p.N_shots = 4
        self.p.N_repeats = 1

        self.p.t_tof = 4500.e-6

        #MOT detunings

        # self.p.detune_d1_c_d1cmot = np.linspace(5,6.5,5)
        self.p.V_d1cmot_current = np.linspace(0.2,1.2,8)

        self.p.detune_d2_r_d1cmot = np.linspace(-3.3,-4.8,6)
        # self.p.amp_d2_r_d1cmot = np.linspace(0.04,0.1,9)

        self.xvarnames = ['detune_d2_r_d1cmot','V_d1cmot_current']

        self.get_N_img()

    @kernel
    def cmot_d1(self,t,delta,V):
        delay(-10*us)
        self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_d1cmot,
                                       amplitude=self.params.amp_d1_c_d1cmot)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=delta,
                                       amplitude=self.params.amp_d2_r_d1cmot)
        delay(10*us)
        with parallel:
            self.dds.d2_3d_r.on()
            self.dds.d1_3d_c.on()
            self.dds.d2_3d_c.off()
            self.dds.d1_3d_r.off()
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                      V)
                self.zotino.load()
        delay(t)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for delta in self.p.detune_d2_r_d1cmot:
            for V in self.p.V_d1cmot_current:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot, delta, V)
                
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

        

        


            

        

