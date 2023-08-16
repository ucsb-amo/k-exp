from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

from kexp.util.artiq.async_print import aprint

import numpy as np

class scan_image_detuning(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,andor_imaging=True,absorption_image=False)

        self.run_info._run_description = "scan image detuning"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 30. * 1.e-3

        self.p.N_shots = 100
        self.p.N_repeats = 1
        self.p.t_tof = 10 * 1.e-6 # mot
        
        self.p.xvar_image_detuning = np.linspace(-300.,-100.,self.p.N_shots) * 1.e6
        # self.p.xvar_amp_imaging_fluor = np.linspace(.15,.07,self.p.N_shots)
        self.p.xvar_amp_imaging_fluor = [self.p.amp_imaging_fluor]

        self.camera_params.exposure_time = 20.0e-3

        self.trig_ttl = self.get_device("ttl14")
        
        self.step_time = self.p.t_ramp / self.p.n_gmramp_steps

        self.c_ramp = np.linspace(self.p.v_pd_c_gmramp_start, self.p.v_pd_c_gmramp_end, self.p.n_gmramp_steps)
        self.r_ramp = np.linspace(self.p.v_pd_r_gmramp_start, self.p.v_pd_r_gmramp_end, self.p.n_gmramp_steps)

        self.xvarnames = ['xvar_image_detuning','xvar_amp_imaging_fluor']

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for x_var1 in self.p.xvar_image_detuning:

            for xvar2 in self.p.xvar_amp_imaging_fluor:

                self.set_imaging_detuning(detuning=x_var1)
                self.dds.imaging.set_dds_gamma(amplitude=xvar2)
                self.core.break_realtime()

                # self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                # self.mot(self.p.t_mot_load * s)
                # self.hybrid_mot(self.p.t_mot_load * s)

                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                # self.dds.push.off()
                # self.switch_d2_2d(0)

                # self.cmot_d1(self.p.t_d1cmot * s)

                # self.trig_ttl.on()
                # self.gm(self.p.t_gm * s)

                # # self.dds.tweezer.on()

                # for n in range(self.p.n_gmramp_steps):
                #     self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp[n])
                #     delay_mu(self.params.t_rtio_mu)
                #     self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp[n])
                #     delay(self.step_time)

                # self.dds.tweezer.on()
                
                self.trig_ttl.off()
                delay(2*ms)
                self.switch_d1_3d(0)

                delay(self.p.t_tweezer_hold)

                # self.dds.tweezer.off()

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