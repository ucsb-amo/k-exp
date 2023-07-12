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

        self.p.t_tof = np.linspace(500,900,5) * 1.e-6

        self.p.xvar_detune_push = np.linspace(-7.,1.,5)

        #GM Detunings
        # self.p.xvar_v_pd_d1_r_gm = np.linspace(.03,.188,6)

        self.xvarnames = ['xvar_detune_push','t_tof']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_detune_push:
            for tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s, detune_push=xvar)

                self.dds.push.off()
                self.switch_d2_2d(0)

                # self.gm_ramp(self.p.t_gm_ramp)
                
                self.release()
                
                ### abs img
                delay(tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.p.detune_push = self.p.xvar_detune_push

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
