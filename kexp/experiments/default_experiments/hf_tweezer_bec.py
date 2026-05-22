
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(100.,2000.,10)*1.e-6)
        self.p.t_tof = 2.5e-6

        # self.xvar('frequency_detuned_hf_f1m1',-575.e6 + np.arange(-6.,6.+3,3)*1.e6)

        # self.p.v_pd_hf_tweezer_squeeze_power
        from kexp.calibrations.tweezer import tweezer_vpd2_to_vpd1
        vpd1_0 = tweezer_vpd2_to_vpd1(self.p.v_pd_tweezer_squeeze_rampup_handoff_lp)
        # self.xvar('v_pd_hf_tweezer_squeeze_power', np.linspace(vpd1_0, 0.5, 7))
        # self.xvar('v_pd_hf_tweezer_squeeze_power', np.linspace(0.1, 8., 7))
        self.p.v_pd_hf_tweezer_squeeze_power = 8.

        self.p.t_tweezer_hold = 100.e-3
        # self.xvar('t_tweezer_hold', np.linspace(0., 300, 5)*1.e-3)
        self.p.t_tweezer_squeezer_ramp_2 = 20.e-3
        self.xvar('t_tweezer_squeezer_ramp_2', np.linspace(3.,100.,2)*1.e-3)
        self.p.N_repeats = 3
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.prepare_hf_tweezers(squeeze=True)
        
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
