from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mag trap out of gm, image in-situ"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = 3
        self.p.t_mot_load = 0.25

        self.p.t_tof = 10.e-6

        self.p.t_magtrap_on = np.linspace(1.,25.,6) * 1.e-3

        # self.p.frequency_detuned_imaging_F1 = self.p.frequency_detuned_imaging + 461.7e6

        self.xvarnames = ['t_magtrap_on']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for t in self.p.t_magtrap_on:

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()

            # self.cmot_d2(self.p.t_d2cmot * s)
            
            self.ttl.pd_scope_trig.on()
            self.cmot_d1(self.p.t_d1cmot * s)

            self.gm(self.p.t_gm * s)

            self.gm_ramp(self.p.t_gmramp * s)
            self.ttl.pd_scope_trig.off()

            self.switch_d1_3d(0)

            # self.optical_pumping(t=200.e-6,t_bias_rampup=2.e-3,amp_optical_pumping=0.3,amp_optical_pumping_r=0.3,v_zshim_current=9.99)

            self.set_magnet_current(v=9.99)
            self.ttl.magnets.on()
            delay(t)
            self.ttl.magnets.off()

            ### abs img
            delay(self.p.t_tof * s)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

            self.set_magnet_current(v=self.p.v_mot_current)
            delay(0.1)
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")