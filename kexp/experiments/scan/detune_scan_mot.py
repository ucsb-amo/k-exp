from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
import numpy as np

class detune_scan_mot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 1

        self.p.N_shots = 30
        self.p.N_repeats = 1

        self.p.t_tof = 1000.e-6

        #MOT detunings

        self.p.x_detune_d2_c_mot = np.linspace(-0.5,-1.5,self.p.N_shots)
        self.p.amp_d2_c_mot = self.dds.d2_3d_c.amplitude
        self.p.x_detune_d2_r_mot = np.linspace(-4.5,-5.5,self.p.N_shots)
        self.p.amp_d2_r_mot = self.dds.d2_3d_r.amplitude

        self.xvarnames = ['x_detune_d2_c_mot','x_detune_d2_r_mot']

        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for delta_c in self.p.x_detune_d2_c_mot:
            for delta_r in self.p.x_detune_d2_r_mot:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s, detune_d2_c=delta_c, detune_d2_r=delta_r)

                self.dds.push.off()
                self.switch_d2_2d(0)
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.p.detune_d2_c_mot = self.p.x_detune_d2_c_mot
        self.p.detune_d2_r_mot = self.p.x_detune_d2_r_mot
        
        self.ds.save_data(self)

        print("Done!")

        

        


            

        

