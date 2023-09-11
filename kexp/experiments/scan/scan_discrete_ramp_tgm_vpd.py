from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class scan_discrete_ramp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "gm tof, vary discrete ramp params"

        ## Parameters

        self.p = self.params

        #Ramp params

        self.p.N_shots = 6
        self.p.N_repeats = [2,2]
        self.p.v_pd_gmramp_end = np.linspace(0.8,1.5,self.p.N_shots)

        self.c_ramp = np.zeros((len(self.p.v_pd_gmramp_end), self.p.n_gmramp_steps))
        self.r_ramp = np.zeros((len(self.p.v_pd_gmramp_end), self.p.n_gmramp_steps))

        # self.p.t_tof = np.linspace(3000.,7000.,8) * 1.e-6

        self.p.t_tof = 3000.e-6
        self.p.xvar_t_gmramp = np.linspace(1.,7.,7) * 1.e-3

        for idx1 in range(len(self.p.v_pd_gmramp_end)):
                self.c_ramp[idx1][:] = np.linspace(self.p.v_pd_c_gmramp_start, self.p.v_pd_gmramp_end[idx1], self.p.n_gmramp_steps)
                self.r_ramp[idx1][:] = np.linspace(self.p.v_pd_r_gmramp_start, self.p.v_pd_gmramp_end[idx1], self.p.n_gmramp_steps)

        # self.xvarnames = ['v_pd_gmramp_end','t_tof']
        self.xvarnames = ['v_pd_gmramp_end','xvar_t_gmramp']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for idx1 in range(len(self.p.v_pd_gmramp_end)):
            for t in self.p.xvar_t_gmramp:

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                dt_gmramp = t / self.p.n_gmramp_steps
                for n in range(self.p.n_gmramp_steps):
                    self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp[idx1][n])
                    delay_mu(self.params.t_rtio_mu)
                    self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp[idx1][n])

                    with parallel:
                        self.ttl_magnets.off()
                        self.switch_d1_3d(1)
                        self.switch_d2_3d(0)
                    delay(dt_gmramp)

                # delay(self.p.t_gm * s)

                self.trig_ttl.off()
                
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
