from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.analysis.base_analysis import atomdata
from kexp.base.base import Base
import numpy as np

class gm_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "GM v_pd_c scan"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000,8000,5) * 1.e-6
        self.p.t_tof = 2000.e-6

        #GM Detunings
        self.p.N_shots = 5
        self.p.N_repeats = 1

        # self.p.xvar_detune_gm = np.linspace(1.,5.,self.p.N_shots)
        self.p.xvar_v_pd_d1_r_gm = np.linspace(0.5,1.8,self.p.N_shots)

        # self.xvarnames = ['xvar_detune_c_gm','xvar_detune_r_gm']
        self.xvarnames = ['xvar_v_pd_d1_r_gm']

        # vars(self.p)[self.xvarnames[0]] = np.repeat(vars(self.p)[self.xvarnames[0]],self.p.N_repeats)
        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar_1 in self.p.xvar_v_pd_d1_r_gm:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d2cmot * s)

            self.gm(self.p.t_gm * s, v_pd_d1_r=xvar_1)

            # self.gm_ramp(self.p.t_gm_ramp)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
