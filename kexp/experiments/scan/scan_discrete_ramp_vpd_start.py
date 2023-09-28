from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class scan_discrete_ramp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof, vary discrete ramp params"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000.,7000.,3) * 1.e-6
        self.p.t_tof = 13000 * 1.e-6

        #Ramp params

        self.p.N_repeats = [1,1]
        self.p.v_pd_c_gmramp_start = np.linspace(5.,3.,7)
        self.p.v_pd_r_gmramp_start = np.linspace(5.,3.,7)

        self.t_step_time = self.p.t_gmramp / self.p.n_gmramp_steps

        self.xvarnames = ['v_pd_c_gmramp_start','v_pd_r_gmramp_start']

        self.finish_build()
        
        self.c_ramp = np.zeros((len(self.p.v_pd_c_gmramp_start), len(self.p.v_pd_r_gmramp_start), self.p.n_gmramp_steps))
        self.r_ramp = np.zeros((len(self.p.v_pd_c_gmramp_start), len(self.p.v_pd_r_gmramp_start), self.p.n_gmramp_steps))

        for idx1 in range(len(self.p.v_pd_c_gmramp_start)):
            for idx2 in range(len(self.p.v_pd_r_gmramp_start)):
                self.c_ramp[idx1][idx2][:] = np.linspace(self.p.v_pd_c_gmramp_start[idx1], self.p.v_pd_c_gmramp_end, self.p.n_gmramp_steps)
                self.r_ramp[idx1][idx2][:] = np.linspace(self.p.v_pd_r_gmramp_start[idx2], self.p.v_pd_r_gmramp_end, self.p.n_gmramp_steps)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for idx1 in range(len(self.p.v_pd_c_gmramp_start)):
            for idx2 in range(len(self.p.v_pd_r_gmramp_start)):

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                # self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                with parallel:
                    self.ttl_magnets.off()
                    self.switch_d1_3d(1)
                    self.switch_d2_3d(0)

                for n in range(self.p.n_gmramp_steps):
                    self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp[idx1][idx2][n])
                    delay_mu(self.params.t_rtio_mu)
                    self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp[idx1][idx2][n])
                    delay(self.t_step_time)

                # self.trig_ttl.off()
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
