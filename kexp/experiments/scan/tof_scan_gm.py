from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class tof_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "GM tof, vary detune"

        ## Parameters

        self.p = self.params

        self.p.t_tof = np.linspace(11000,16000,6) * 1.e-6

        #GM Detunings
        # self.p.xvar_v_pd_d1_r_gm = np.linspace(1.0,1.3,7)
        self.p.xvar_t_gm = np.linspace(4.0,12.0,5) * 1.e-3

        self.xvarnames = ['xvar_t_gm','t_tof']
        self.p.N_repeats = [1,3]

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_t_gm:
            for tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d2cmot * s)

                self.gm(xvar * s)

                # self.gm_ramp(self.p.t_gm_ramp)
                
                self.release()
                
                ### abs img
                delay(tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        # self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
