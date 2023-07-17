from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class scan_gm_params(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "GM v_pd_d1_c_gm vs v_pd_r"
        # self.run_info._run_description = "GM detune_c vs detune_r"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000,8000,5) * 1.e-6
        self.p.t_tof = 3500.e-6

        #GM Detunings
        # self.p.xvar_detune_gm = np.linspace(5.5,7.0,5)
        # self.p.xvar_detune_d1_c_gm = np.linspace(5.5,9.0,5)
        # self.p.xvar_detune_d1_r_gm = np.linspace(5.5,9.0,5)
        self.p.xvar_v_pd_d1_c_gm = np.linspace(1.0,5.,5)
        self.p.xvar_v_pd_d1_r_gm = np.linspace(.5,1.3,5)

        self.xvarnames = ['xvar_v_pd_d1_c_gm','xvar_v_pd_d1_r_gm']
        # self.xvarnames = ['xvar_detune_d1_gm', 'xvar_detune_d1_r_gm']
        # self.xvarnames = ['xvar_detune_gm', 'xvar_v_pd_d1_r_gm']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar_1 in self.p.xvar_v_pd_d1_c_gm:
            for xvar_2 in self.p.xvar_v_pd_d1_r_gm:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.gm(self.p.t_gm * s, v_pd_d1_c=xvar_1, v_pd_d1_r=xvar_2)

                # self.gm_ramp(self.p.t_gm_ramp)
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        # self.p.detune_gm = self.p.xvar_detune_gm
        self.p.v_pd_d1_c_gm = self.p.xvar_v_pd_d1_c_gm
        self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        # self.p.detune_d1_c_gm = self.p.xvar_detune_d1_c_gm
        # self.p.detune_d1_r_gm = self.p.xvar_detune_d1_r_gm
# 
        # self.p.v_pd_d1_c_gm = self.p.xvar_v_pd_d1_c_gm
        # self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
