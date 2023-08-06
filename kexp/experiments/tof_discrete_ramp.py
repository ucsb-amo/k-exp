from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof_discrete_ramp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 30. * 1.e-3

        self.p.t_andor_expose = 50. * 1.e-3

        self.p.N_shots = 5
        self.p.N_repeats = 3

        # self.p.t_tof = np.linspace(1000,2000,self.p.N_shots) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(400,1250,self.p.N_shots) * 1.e-6 # cmot
        # self.p.t_tof = np.linspace(1000,3000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(10000,15000,self.p.N_shots) * 1.e-6 # d1 cmot
        self.p.t_tof = np.linspace(3000,7000,self.p.N_shots) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # tweezer
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # mot_reload

        # self.p.amp_push = 0.

        self.step_time = self.p.t_ramp / self.p.steps

        self.c_ramp = np.linspace(self.p.c_ramp_start, self.p.c_ramp_end, self.p.steps)
        self.r_ramp = np.linspace(self.p.r_ramp_start, self.p.r_ramp_end, self.p.steps)

        self.xvarnames = ['t_tof']

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

            self.trig_ttl.on()
            self.gm(self.p.t_gm * s)
            
            for n in range(self.p.steps):
                delay(-10*us)
                self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp[n])
                delay_mu(self.params.t_rtio_mu)
                self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp[n])
                delay(10*us)

                with parallel:
                    self.ttl_magnets.off()
                    self.switch_d1_3d(1)
                    self.switch_d2_3d(0)
                delay(self.step_time)

            # delay(self.p.t_gm * s)

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