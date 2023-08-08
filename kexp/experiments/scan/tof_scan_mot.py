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

        # self.p.xvar_amp_push = np.linspace(.00,.2,5)

        # self.p.xvar_detune_push = np.linspace(-4.0,4.,5)

        # self.p.xvar_v_mot_current = np.linspace(.7,.9,5)

        # self.p.xvar_v_d1cmot_current = np.linspace(0.2,.6,5)

        # self.p.xvar_t_gm = np.linspace(.3,2.,5) * 1.e-3

        # self.p.xvar_t_d1cmot = np.linspace(.3,10.,5) * 1.e-3

        #GM Detunings
        self.p.xvar_v_pd_d1_c_gm = np.linspace(2.,1.,5)
        self.p.xvar_v_pd_d1_r_gm = np.linspace(2.,1.,5)
        # self.p.xvar_detune_gm = np.linspace(7.,8.7,5)

        self.xvarnames = ['xvar_v_pd_d1_r_gm','t_tof']

        self.finish_build()

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

                self.gm(self.p.t_gm * s, v_pd_d1_r=xvar)
                
                self.release()
                
                ### abs img
                delay(tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        # self.p.detune_gm = self.p.xvar_detune_gm

        # self.p.detune_push = self.p.xvar_detune_push
        # self.p.amp_push = self.p.xvar_amp_push

        # self.p.v_mot_current = self.p.xvar_v_mot_current
        
        # self.p.v_d1cmot_current = self.p.xvar_v_d1cmot_current
        
        # self.p.t_gm = self.p.xvar_t_gm
        # self.p.t_d1cmot = self.p.xvar_t_d1cmot

        # self.p.v_pd_d1_c_gm = self.p.xvar_v_pd_d1_c_gm
        self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
