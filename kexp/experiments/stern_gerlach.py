from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params

import numpy as np

class sg(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)
        # self.camera_params.serial_no = camera_params.basler_fluor_camera_params.serial_no
        # self.camera_params.magnification = camera_params.basler_fluor_camera_params.magnification

        self.run_info._run_description = "SG"

        ## Parameters

        self.p = self.params

        N = 8
        self.p.N_repeats = 1

        self.p.t_tof = np.linspace(17000,25000,N) * 1.e-6 # gm

        self.xvarnames = ['t_tof']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for t_tof in self.p.t_tof:

            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp * s)
            self.release()

            # self.flash_repump(t=150.e-6,amp=0.188)

            # self.set_zshim_magnet_current(v=9.99)
            self.ttl_magnets.on()

            ### abs img
            delay(t_tof * s)
            self.ttl_magnets.off()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

            self.set_zshim_magnet_current()

            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")