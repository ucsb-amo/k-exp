from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class tof_scan_mot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof, vary coil current"

        ## Parameters

        self.p = self.params

        self.p.t_tof = np.linspace(2000,3500,5) * 1.e-6

        # self.p.xvar_amp_push = np.linspace(.1,.31,8)
        # self.p.xvar_v_d1cmot_current = np.linspace(.9,1.6,5)

        #GM Detunings
        self.p.xvar_v_pd_d1_r_gm = np.linspace(.95,1.2,5)

        self.xvarnames = ['xvar_v_pd_d1_r_gm','t_tof']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_v_pd_d1_r_gm:
            for tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.gm(self.p.t_gm * s, v_pd_d1_r = xvar)
                
                self.release()
                
                ### abs img
                delay(tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.p.v_d1cmot_current = self.p.xvar_v_pd_d1_r_gm

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
