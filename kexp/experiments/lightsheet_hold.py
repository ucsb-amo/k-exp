from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config.dds_calibration import DDS_VVA_Calibration
from kexp.config.ttl_id import ttl_frame
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=False, absorption_image=False, andor_imaging=True)
        Base.__init__(self)

        self.run_info._run_description = "scan lightsheet hold"

        ## Parameters

        self.p = self.params

        self.p.t_mot_load = 1.5

        # self.camera_params.exposure_time = 50.e-3

        self.p.xvar_t_lightsheet_hold = np.linspace(2.,20.,10) * 1.e-3
        self.p.xvar_t_tweezer_hold = np.linspace(0.,1.,5) * 1.e-3
        self.p.xvar_t_gm_pump = np.linspace(0.,800.,10) * 1.e-6
        self.p.xvar_t_tof = np.linspace(5.,500.,5) * 1.e-6

        self.xvarnames = ['xvar_t_lightsheet_hold']

        self.p.N_repeats = 1

        self.finish_build(shuffle=True)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        for xvar in self.p.xvar_t_lightsheet_hold:

            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp * s) 
            # self.dds.d1_3d_c.off()
            # delay(xvar)
            # self.dds.d1_3d_r.off()

            self.release()

            # self.set_zshim_magnet_current(v = 9.)
            
            # self.set_magnet_current(v=3.)
            # self.ttl.magnets.on()
            
            self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

            delay(xvar)

            self.lightsheet.off()
            
            delay(10.e-6*s)

            # delay(xvar * s)
            self.flash_repump()
            # self.fl_image()
            self.abs_image()

            # self.dds.second_imaging.off()
            
            self.core.break_realtime()
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")