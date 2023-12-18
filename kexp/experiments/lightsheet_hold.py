from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config.dds_calibration import DDS_VVA_Calibration
from kexp.config.ttl_id import ttl_frame
from kexp.util.artiq.async_print import aprint

import numpy as np

class lightsheet_hold(EnvExperiment, Base):

    def build(self):
        Base.__init__(self, basler_imaging=False, absorption_image=True, andor_imaging=True)
        # Base.__init__(self)

        self.camera_params.em_gain = 100.
        self.camera_params.exposure_time = 5.e-6

        self.run_info._run_description = "scan lightsheet hold"

        ## Parameters

        self.p = self.params

        self.p.t_mot_load = 1.
        self.p.amp_imaging_abs = 0.315

        # self.camera_params.exposure_time = 50.e-3

        # self.p.xvar_t_lightsheet_hold = np.logspace( np.log10(5.e-3), np.log10(20.), 10)
        # self.p.xvar_t_lightsheet_hold = np.linspace(5.,10.,2) * 1.e-3
        # self.p.xvar_amp_imaging_abs = np.linspace(.2,.4,7)
        # self.p.xvar_t_tweezer_hold = np.linspace(0.,1.,5) * 1.e-3
        # self.p.xvar_t_tweezer_ramp = np.linspace(0.,20.,8) * 1.e-3
        self.p.xvar_f_tweezer = np.linspace(72.5,76.,10) * 1.e6
        # self.p.xvar_t_gm_pump = np.linspace(0.,800.,10) * 1.e-6
        # self.p.xvar_t_tof = np.linspace(5.,500.,5) * 1.e-6

        self.p.xvar_tweezer_ramp_end = np.linspace(.05,.16,8)
        self.tweezer_ramp_start = 0.
        self.p.xvar_tweezer_ramps = []
        for ep in self.p.xvar_tweezer_ramp_end:
            self.p.xvar_tweezer_ramps.append(np.linspace(self.tweezer_ramp_start,ep,self.p.n_tweezer_1064_ramp_steps))

        self.xvarnames = ['xvar_f_tweezer']

        self.p.N_repeats = 1

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        for xvar in self.p.xvar_f_tweezer:

            # # self.dds.tweezer_aod.set_dds(frequency=self.params.frequency_aod_1064,amplitude=.25)
            # self.dds.imaging.set_dds(amplitude=xvar)

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
            
            # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
            # delay(100.e-3)
            self.tweezer_1064_ramp(t_tweezer_1064_ramp=9.e-3,tweezer_frequency=xvar)
            # self.dds.tweezer_aod.on()
            # delay(10.e-3)
            # self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampup)
            delay(20.e-3)
            # self.lightsheet.off()
            # delay(1.e-3)
            self.dds.tweezer_aod.off()
            
            delay(10.e-6*s)

            # delay(xvar * s)
            self.flash_repump()
            # self.fl_image()
            self.abs_image()
            # self.dds.tweezer_aod.off()
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