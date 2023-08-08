from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class oneshot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,absorption_image=False,basler_imaging=True)
        # Base.__init__(self,setup_camera=False)

        self.run_info._run_description = "gm with fluorescence camera"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 1
        self.p.N_repeats = 1
        self.p.t_tof = 500.e-6

        self.p.dummy = np.linspace(1.,1.,self.p.N_shots)

        
        self.step_time = self.p.t_ramp / self.p.n_gmramp_steps

        self.c_ramp = np.linspace(self.p.v_pd_c_gmramp_start, self.p.v_pd_c_gmramp_end, self.p.n_gmramp_steps)
        self.r_ramp = np.linspace(self.p.v_pd_r_gmramp_start, self.p.v_pd_r_gmramp_end, self.p.n_gmramp_steps)

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['dummy']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        self.dds.tweezer.on()
        
        for _ in self.p.dummy:

            self.set_imaging_detuning()
            self.dds.imaging.set_dds(amplitude=.3)
            self.core.break_realtime()

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            self.trig_ttl.on()
            self.gm(self.p.t_gm * s)

            # self.dds.tweezer.on()

            for n in range(self.p.n_gmramp_steps):
                self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp[n])
                delay_mu(self.params.t_rtio_mu)
                self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp[n])
                delay(self.step_time)
            
            # self.trig_ttl.off()
            self.switch_d1_3d(0)
            
            # delay(self.p.t_tweezer_hold)

            # delay(8*ms)

            # self.switch_d1_3d(1)
            self.fl_image()

            # self.gm_ramp(self.p.t_gm_ramp * s)

            # self.mot_reload(self.p.t_mot_reload * s)
            
            self.release()
            
            ### abs img
            # delay(self.p.t_tof * s)
            # self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")