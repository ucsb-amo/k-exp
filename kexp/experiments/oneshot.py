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

        
        self.step_time = self.p.t_ramp / self.p.steps

        self.c_ramp = np.linspace(self.p.c_ramp_start, self.p.c_ramp_end, self.p.steps)
        self.r_ramp = np.linspace(self.p.r_ramp_start, self.p.r_ramp_end, self.p.steps)

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
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)

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
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.fl_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")