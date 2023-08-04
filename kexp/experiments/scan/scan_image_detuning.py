from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

from kexp.util.artiq.async_print import aprint

import numpy as np

class scan_image_detuning(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,andor_imaging=True)

        self.run_info._run_description = "scan image detuning"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 20. * 1.e-3

        self.p.t_andor_expose = 50. * 1.e-3

        self.p.N_shots = 7
        self.p.N_repeats = 1
        self.p.t_tof = 20 * 1.e-6 # mot
        
        self.p.xvar_image_detuning = np.linspace(-290.,-280.,self.p.N_shots) * 1.e6

        self.camera_params.exposure_time = 20.0e-3

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

        self.xvarnames = ['xvar_image_detuning']

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for x_var in self.p.xvar_image_detuning:

            self.set_imaging_detuning(detuning=x_var)

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            # self.gm(self.p.t_gm * s)

            self.trig_ttl.on()
            self.gm(self.p.t_gm * s)
            self.dds.tweezer.on()
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

            self.trig_ttl.off()

            delay(self.p.t_tweezer_hold)

            self.fl_image(detuning=x_var, with_light=True)

            # self.gm_ramp(self.p.t_gm_ramp * s)

            # self.mot_reload(self.p.t_mot_reload * s)
            
            self.release()
            
            ### abs img
            # delay(self.p.t_tof * s)
            # self.abs_image(detuning=x_var)

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")