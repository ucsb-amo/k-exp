from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(0.2,1.8,8))
        self.p.v_hf_tweezer_paint_amp_max = 1.3

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(1.5,5.,8))
        self.p.v_pd_hf_tweezer_1064_rampdown3_end = 2.5
# 
        # self.xvar('i_hf_tweezer_load_current',np.linspace(192.,195.,8))
        self.p.i_hf_tweezer_load_current = 192.86

        self.p.amp_imaging = .2

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,300.e-3,10))
        self.p.t_tweezer_hold = .1e-3

        # self.xvar('t_tof',np.linspace(1500.,4500.,10)*1.e-6) 
        self.p.t_tof = 2500.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 21

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(ramp_down_painting=False,squeeze=False)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)