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

        self.p.t_gm_ramp = 5.e-3

        self.core_dma

        self.p.N_shots = 5
        self.p.N_repeats = 1
        # self.p.t_tof = np.linspace(500,1500,self.p.N_shots) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(400,1250,self.p.N_shots) * 1.e-6 # cmot
        # self.p.t_tof = np.linspace(1000,3000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(10000,15000,self.p.N_shots) * 1.e-6 # d1 cmot
        self.p.t_tof = np.linspace(3000,6000,self.p.N_shots) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # tweezer
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # mot_reload

        # self.p.amp_push = 0.

        self.xvarnames = ['t_tof']

        N, dt = self.dds.get_ramp_dt(self.p.t_gm_ramp)

        a_ic, a_ir = self.dds.d1_3d_c.amplitude, self.dds.d1_3d_r.amplitude
        self.p.amp_div_gm_ramp = 2.
        a_c = np.linspace(a_ic,a_ic/self.p.amp_div_gm_ramp,N)
        a_r = np.linspace(a_ir,a_ic/self.p.amp_div_gm_ramp,N)

        self.dds.set_amplitude_ramp_profile(self.dds.d1_3d_c,amp_list=a_c,dt_ramp=dt,dds_mgr_idx=0)
        self.dds.set_amplitude_ramp_profile(self.dds.d1_3d_r,amp_list=a_r,dt_ramp=dt,dds_mgr_idx=0)

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t_tof in self.p.t_tof:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            # self.gm(self.p.t_gm * s)

            # self.gm_tweezer(self.p.t_tweezer_hold * s)

            self.trig_ttl.on()
            self.gm(self.p.t_gm)
            # self.gm_ramp(t=self.p.t_gm, t_ramp=self.p.t_gm_ramp)
            self.trig_ttl.off()

            # self.mot_reload(self.p.t_mot_reload * s)
            
            self.release()
            
            ### abs img
            delay(t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")