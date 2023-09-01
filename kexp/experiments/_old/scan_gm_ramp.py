from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 30. * 1.e-3

        self.p.t_andor_expose = 50. * 1.e-3

        self.p.N_shots = 5
        self.p.N_repeats = 1
        self.p.t_tof = 3000 * 1.e-6 # gm

        # self.p.amp_push = 0.

        self.p.t_gm_ramp = 4.e-3
        self.p.amp_frac_gm_ramp = np.linspace(0.1,1.0,5)

        self.xvarnames = ['amp_frac_gm_ramp']

        self.idx = 0
        for ii in range(len(self.p.amp_frac_gm_ramp)):

            N, dt = self.dds.get_ramp_dt(self.p.t_gm_ramp)

            a_ic, a_ir = self.dds.d1_3d_c.amplitude, self.dds.d1_3d_r.amplitude
            a_c = np.linspace(1,self.p.amp_frac_gm_ramp[ii],N)*a_ic
            a_r = np.linspace(1,self.p.amp_frac_gm_ramp[ii],N)*a_ir

            self.dds.set_amplitude_ramp_profile(self.dds.d1_3d_c,amp_list=a_c,dt_ramp=dt,dds_mgr_idx=self.idx)
            self.dds.set_amplitude_ramp_profile(self.dds.d1_3d_r,amp_list=a_r,dt_ramp=dt,dds_mgr_idx=self.idx)

            self.idx += 1

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for idx in range(self.idx):
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)
                # self.hybrid_mot(self.p.t_mot_load * s)

                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                # self.gm_ramp(self.p.t_gm, self.p.t_gm_ramp, dds_mgr_idx=idx)
                self.gm(self.p.t_gm+self.p.t_gm_ramp)
                self.trig_ttl.off()
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")