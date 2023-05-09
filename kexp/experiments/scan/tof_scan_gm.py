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

        # self.p.N_shots = 5

        # self.p.N_repeats = 1
        # self.p.t_tof = np.linspace(3000,8000,self.p.N_shots) * 1.e-6
        # self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        self.p.t_tof = 3000.e-6

        #GM Detunings
        self.params.xvar_detune_c = np.linspace(3.,6.,7)
        self.params.xvar_detune_r = np.linspace(3.,6.,7)

        self.xvarnames = ['xvar_detune_c','xvar_detune_r']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for delta_c in self.p.xvar_detune_c:
            for delta_r in self.p.xvar_detune_r:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d2cmot * s)

                self.gm(self.p.t_gm * s, detune_d1_c=delta_c, detune_d1_r=delta_r)
                
                self.release()
                
                ### abs img
                delay(self.params.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.params.detune_d1_c_gm = self.params.xvar_detune_c
        self.params.detune_d1_r_gm = self.params.xvar_detune_r

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")

        

        


            

        

