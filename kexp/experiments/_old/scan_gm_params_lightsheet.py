from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class scan_gm_params(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,andor_imaging=False)

        self.run_info._run_description = "scan gm detuning with light sheet load"
        # self.run_info._run_description = "GM detune_c vs detune_r"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000,8000,5) * 1.e-6
        self.p.t_tof = 100.e-6

        #GM Detunings
        self.p.xvar_detune_gm = np.linspace(6.0,8.5,5)
        # self.p.xvar_detune_d1_c_gm = np.linspace(5.5,9.0,5)
        # self.p.xvar_detune_d1_r_gm = np.linspace(5.5,9.0,5)
        # self.p.xvar_v_pd_d1_c_gm = np.linspace(1.5,5.,7)
        # self.p.xvar_v_pd_d1_r_gm = np.linspace(1.5,5.,7)
        # self.p.xvar_v_pd_d1_r_gm = np.linspace(1.5,5.,7)

        self.xvarnames = ['xvar_detune_gm']
        # self.xvarnames = ['xvar_detune_d1_gm', 'xvar_detune_d1_r_gm']
        # self.xvarnames = ['xvar_detune_gm', 'xvar_v_pd_d1_r_gm']

        self.p.t_lightsheet_hold = 10.e-3

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar_1 in self.p.xvar_detune_gm:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)

            self.dds.lightsheet.set_dds(v_pd=5.0)
            self.dds.lightsheet.on()

            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            self.gm(self.p.t_gm * s, detune_d1=xvar_1)

            delay(self.p.t_lightsheet_load)
            
            self.release()
            
            delay(self.p.t_lightsheet_hold)
            self.dds.lightsheet.off()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.p.detune_gm = self.p.xvar_detune_gm
        # self.p.v_pd_d1_c_gm = self.p.xvar_v_pd_d1_c_gm
        # self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        # self.p.detune_d1_c_gm = self.p.xvar_detune_d1_c_gm
        # self.p.detune_d1_r_gm = self.p.xvar_detune_d1_r_gm
 
        # self.p.v_pd_d1_c_gm = self.p.xvar_v_pd_d1_c_gm
        # self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
