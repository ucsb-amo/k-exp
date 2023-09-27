from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "scan lightsheet hold"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(1200,2000,self.p.N_shots) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(2000,3500,self.p.N_shots) * 1.e-6 # cmot
        # self.p.t_tof = np.linspace(1000,3000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(6000,9000,self.p.N_shots) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(7000,10000,self.p.N_shots) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # tweezer
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # mot_reload

        self.p.xvar_t_lightsheet_hold = np.linspace(12.,30.,10) * 1.e-3

        # self.p.xvar_v_d1cmot_current = np.linspace(.5,1.8,10)

        # self.p.xvar_v_d2cmot_current = np.linspace(.5,1.8,10)

        self.xvarnames = ['xvar_t_lightsheet_hold']
        # self.xvarnames = ['xvar_v_d1cmot_current']
        # self.xvarnames = ['xvar_v_d2cmot_current']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_t_lightsheet_hold:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            self.dds.lightsheet.set_dds(v_pd=5.)
            
            ### GM 1 ###
            self.gm(self.p.t_gm * s)

            self.gm_ramp(self.p.t_gmramp * s)

            # delay(self.p.t_lightsheet_load)
            
            self.release()

            self.dds.lightsheet.on()

            ### GM 2 ###
            # self.gm(t=2.e-3*s, detune_d1=11., v_pd_d1_c=4.5, v_pd_d1_r=4.)

            self.release()

            # self.pulse_resonant_mot_beams(1.e-6*s)

            delay(xvar)
            self.dds.lightsheet.off()
            
            delay(10.e-6)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.p.t_lightsheet_hold = self.p.xvar_t_lightsheet_hold

        # self.p.v_d1cmot_current = self.p.xvar_v_d1cmot_current

        # self.p.v_d2cmot_current = self.p.xvar_v_d2cmot_current

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")