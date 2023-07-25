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

        self.p.t_tof = np.linspace(3000.,7000.,5) * 1.e-6

        # self.p.xvar_amp_push = np.linspace(.00,.51,5)
        # self.p.xvar_v_d1cmot_current = np.linspace(0.0,.9,5)

        #GM Detunings

        # self.p.xvar_v_pd_d1_c_gm = np.linspace(2.5,4.2,5)
        self.p.xvar_detune_gm = np.linspace(6.5,8.0,5)

        # self.p.xvar_t_gm = np.linspace(2.e-3,5.e-3,5)

        self.xvarnames = ['xvar_detune_gm','t_tof']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_detune_gm:
            for tof in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s,)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.gm(self.p.t_gm * s, detune_d1_c = xvar, detune_d1_r = xvar)
                
                self.release()
                
                ### abs img
                delay(tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.p.detune_gm = self.p.xvar_detune_gm

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
