from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class scan_mot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "optimize mot amps"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 5
        self.p.N_repeats = 1

        self.p.t_tof = 1500.e-6

        # self.p.xvar_detune_d2_c_mot = np.linspace(-3.5,-.75,self.p.N_shots)
        # self.p.xvar_detune_d2_r_mot = np.linspace(-5.,-4.,self.p.N_shots)

        # self.p.xvar_amp_d2_c_mot = np.linspace(.1,.188,self.p.N_shots)
        # self.p.xvar_amp_d2_r_mot = np.linspace(.1,.188,self.p.N_shots)

        self.p.xvar_detune_d1_c_mot = np.linspace(-1.,1.,self.p.N_shots)
        self.p.xvar_detune_d1_r_mot = np.linspace(-1.,1.,self.p.N_shots)

        # self.p.xvar_v_pd_d1_c_mot = np.linspace(2,.5,self.p.N_shots)
        # self.p.xvar_v_pd_d1_r_mot = np.linspace(5.5,3.,self.p.N_shots)

        # self.xvarnames = ['xvar_detune_d2_c_mot','xvar_detune_d2_r_mot']
        
        self.xvarnames = ['xvar_detune_d1_c_mot','xvar_detune_d1_r_mot']
        # self.xvarnames = ['xvar_amp_d2_c_mot','xvar_amp_d2_r_mot']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar1 in self.p.xvar_detune_d1_c_mot:
            for xvar2 in self.p.xvar_detune_d1_r_mot:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s, amp_d2_c=xvar1, amp_d2_r=xvar2)
                # self.mot(self.p.t_mot_load * s, detune_d2_c=xvar1, detune_d2_r=xvar2)

                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                self.dds.push.off()
                # self.switch_d2_2d(0)

                # self.cmot_d2(self.p.t_d2cmot * s)

                # self.cmot_d1(self.p.t_d1cmot * s)

                # self.trig_ttl.on()
                # self.gm(self.p.t_gm * s)

                # self.gm_ramp(self.p.t_gmramp * s)
                # self.trig_ttl.off()

                self.release()

                delay(self.p.t_tof)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        # self.p.detune_d2_c_mot = self.p.xvar_detune_d2_c_mot
        # self.p.detune_d2_r_mot = self.p.xvar_detune_d2_r_mot
        
        # self.p.amp_d2_c_mot = self.p.xvar_amp_d2_c_mot
        # self.p.amp_d2_r_mot = self.p.xvar_amp_d2_r_mot

        # self.p.v_pd_d1_c_mot = self.p.xvar_v_pd_d1_c_mot
        # self.p.v_pd_d1_r_mot = self.p.xvar_v_pd_d1_r_mot

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")