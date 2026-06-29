from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu
from kexp.util.artiq.async_print import aprint

class hf_monitored_rabi(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.p.v_pd_hf_tweezer_squeeze_power = 1.97
        
        # self.xvar('amp_imaging',np.linspace(.2,1.5, 10))
        self.p.amp_imaging = .2

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.e-3,100.e-3,15))
        # self.p.t_tweezer_paint_rampdown = 11.e-3

        # self.xvar('t_tweezer_squeezer_ramp_1',np.linspace(1.1e-3,30.e-3,10))
        # self.p.t_tweezer_squeezer_ramp_1 = 15.e-3

        # self.xvar('t_tweezer_squeezer_ramp_2',np.linspace(3.e-3,100.e-3,15))
        # self.p.t_tweezer_squeezer_ramp_2 = 15.e-3

        self.xvar('t_tof',np.linspace(80.,300.,10)*1.e-6)

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 200.e-6
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 5

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(ramp_down_painting=True,squeeze=True)

        delay(20.e-3)

        # delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        # aprint(self.scope._data)
        self.end(expt_filepath)