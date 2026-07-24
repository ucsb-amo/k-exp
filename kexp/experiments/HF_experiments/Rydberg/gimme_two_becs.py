
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.t_tof = 100.e-6
        # self.xvar('t_tof',np.linspace(400.,3600.,7)*1.e-6)
        # self.xvar('self.p.t_tof',[100*(1.e-6),1500*(1.e-6)])

        self.p.N_repeats = 10
        self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-2.5,-1.5,10))
        # self.tweezer.add_tweezer_list(frequency_list=[74.5e6, 75.5e6],
        #                               amplitude_list=[0.165, 0.17])
        # self.xvar('amp_center',np.linspace(0.165,0.19,5))
        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(4.3,7,5))
        self.p.v_pd_hf_tweezer_1064_rampdown3_end=9.9
        self.p.frequency_tweezer_list=[74.5e6, 75.5e6]
        self.p.amp_tweezer_list = [0.24,0.25]

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.p.amp_tweezer_list = [self.p.amp_center-0.025, self.p.amp_center+0.025]

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.prepare_hf_tweezers(squeeze=False, do_tweezer_evap_3=False)

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
