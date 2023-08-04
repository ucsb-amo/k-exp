from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

from kexp.config import camera_params

class flourescence(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,andor_imaging=True)

        self.run_info._run_description = "oneshot"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 30. * 1.e-3

        self.p.t_load_time = 2 * 1.e-3

        self.camera_params.exposure_time = 5.0e-3

        self.img_detuning = -300.78e6

        self.trig_ttl = self.get_device("ttl14")
        
        self.c_ramp_start = 4.5
        self.c_ramp_end = 1.25

        self.r_ramp_start = 3.1
        self.r_ramp_end = 1.25

        self.t_ramp = 8.e-3

        self.steps = 10
        self.step_time = self.t_ramp / self.steps

        self.c_ramp = np.linspace(self.c_ramp_start, self.c_ramp_end, self.steps)
        self.r_ramp = np.linspace(self.r_ramp_start, self.r_ramp_end, self.steps)

        self.xvarnames = ['dummy']
        self.p.dummy = [1]*2

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.start_triggered_grab()
        delay(self.p.t_grab_start_wait)

        self.kill_mot(self.p.t_mot_kill * s)
        
        for _ in self.p.dummy:
            
            self.set_imaging_detuning(detuning=self.img_detuning)

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
            
            self.mot(self.p.t_load_time * s)

            # self.fl_image()

            self.dds.push.off()
            self.switch_d2_2d(0)
            self.switch_d2_3d(0)

            # self.fl_image()

            self.cmot_d1(self.p.t_d1cmot * s)

            self.trig_ttl.on()
            self.gm(self.p.t_gm * s)
            
            for n in range(self.steps):
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

            self.dds.tweezer.on()

            delay(self.p.t_tweezer_hold)
            
            # self.dds.tweezer.off()
            # self.switch_d1_3d(0)

            self.fl_image(detuning=self.img_detuning, with_light=True)

            self.release()
            
            delay(1*s)

        self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")