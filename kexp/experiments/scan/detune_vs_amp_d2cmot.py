from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
import numpy as np

class detune_vs_amp_d2cmot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "d2 cmot detune vs field gradient"

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        # self.p.N_shots = 4
        self.p.N_repeats = 1

        self.p.t_tof = 750.e-6

        #MOT detuning

        self.p.detune_d2_c_d2cmot = np.linspace(-0.0,-1.75,8)
        self.p.detune_d2_r_d2cmot = self.p.detune_d2_c_d2cmot + -2.
        self.p.V_d2cmot_current = np.linspace(0.7,2.5,10)

        self.xvarnames = ['detune_d2_c_d2cmot','V_d2cmot_current']

        self.get_N_img()

    @kernel
    def cmot_d2(self,t,delta,V):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=delta,
                                    amplitude=self.params.amp_d2_c_d2cmot)
        self.dds.d2_3d_r.set_dds_gamma(delta=delta-2.,
                                    amplitude=self.params.amp_d2_r_d2cmot)
        delay(10*us)
        with parallel:
            self.switch_d2_3d(1)
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

        for delta in self.p.detune_d2_c_d2cmot:
            for V in self.p.V_d2cmot_current:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d2(self.p.t_d2cmot, delta, V)

                # self.cmot_d1(self.p.t_d1cmot)
                
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

        

        


            

        

