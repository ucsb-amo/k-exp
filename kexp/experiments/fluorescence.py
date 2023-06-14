from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

from kexp.config import camera_params

class flourescence(EnvExperiment, Base):

    def build(self):
        Base.__init__(self, absorption_image=False)

        self.run_info._run_description = "oneshot"

        ## Parameters

        self.p = self.params

        self.p.t_andor_expose = .5 * 1.e-3

        self.p.tweezer_hold = 20. * 1.e-3


    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        # delay(-10*us)
        # self.dds.d2_3d_c.set_dds_gamma(delta=0.,
        #                         amplitude=.188)
        # delay_mu(self.params.t_rtio_mu)
        # self.dds.d2_3d_r.set_dds_gamma(delta=0.,
        #                         amplitude=.188)
        # delay(10*us)

        # with parallel:
        #     self.switch_d2_3d(1)
        #     self.ttl_andor.pulse(self.p.t_andor_expose*s)

        self.dds.push.off()
        self.switch_d2_2d(0)
        
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        
        self.mot(self.p.t_mot_load * s)

        # with parallel:
        #     self.ttl_magnets.off()
        #     self.switch_d2_3d(0)
        #     delay_mu(self.params.t_rtio_mu)
        #     self.dds.push.off()

        # delay(-10*us)
        # self.dds.d2_3d_c.set_dds_gamma(delta=0.,
        #                         amplitude=.188)
        # delay_mu(self.params.t_rtio_mu)
        # self.dds.d2_3d_r.set_dds_gamma(delta=0.,
        #                         amplitude=.188)
        # delay(10*us)

        # with parallel:
        #     self.switch_d2_3d(1)
        #     self.ttl_andor.pulse(self.p.t_andor_expose*s)
        
        
        self.cmot_d1(self.p.t_d1cmot * s)

        # self.dds.d2_3d_r.off()
        # self.dds.d1_3d_c.off()

        self.gm(self.p.t_gm * s)

        self.switch_d1_3d(0)

        self.tweezer_trap(self.p.tweezer_hold)

        # delay(self.p.tweezer_hold)
        # delay(5. * 1.e-3)
        
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=0.,
                                amplitude=.188)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=0.,
                                amplitude=.188)
        delay(10*us)

        with parallel:
            self.switch_d2_3d(1)
            self.ttl_andor.pulse(self.p.t_andor_expose*s)
        
        self.release()

        self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        # self.camera.Close()

        # self.ds.save_data(self)

        print("Done!")