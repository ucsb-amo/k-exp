from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class tof_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "cmot tof, vary cmot time"

        ## Parameters

        self.p = self.params

        self.p.t_tof = np.linspace(12001.,18033.,5) * 1.e-6
        # self.p.t_tof = 13.e-3

        #GM Detunings

        # self.p.xvar_detune_gm = np.linspace(5.,12.,4)

        # self.p.xvar_v_pd_d1_r_gm = np.linspace(1.,5.,6)
        # self.p.xvar_v_pd_d1_c_gm = np.linspace(1.,5.,6)
        # self.p.xvar_t_gm = np.linspace(1.0,12.0,6) * 1.e-3

        # self.p.xvar_n_gmramp_steps = np.linspace(10,200,5) * 1.e-6

        # self.p.xvar_v_d1cmot_current = np.linspace(0.3,1.3,6)

        self.p.xvar_t_gmramp = np.linspace(3.,10.,6) * 1.e-3

        # self.p.xvar_v_mot_current = np.linspace(.7,.9,6)

        # self.p.xvar_v_d2cmot_current = np.linspace(0.7,1.5,6)

        # self.xvar_v_d1cmot_current = np.linspace(0.03,.07,5)
        
        # self.p.xvar_v_pd_d1_c_d1cmot = np.linspace(3.,6.0,6)

        # self.p.xvar_detune_d1_c_d1cmot = np.linspace(4.,12.,6)

        # self.p.xvar_t_d2cmot = np.linspace(1.,30.0,6) * 1.e-3

        # self.p.xvar_t_d1cmot = np.linspace(5.,25.0,6) * 1.e-3

        self.xvarnames = ['xvar_t_gmramp','t_tof']
        self.p.N_repeats = [1,1]

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_t_gmramp:
            for t_tof in self.p.t_tof:

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                # self.cmot_d2(self.p.t_d2cmot * s)

                self.cmot_d1(self.p.t_d1cmot)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                self.gm_ramp(t_gmramp=xvar)
                self.trig_ttl.off()
                
                self.release()
                
                ### abs img
                delay(t_tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
