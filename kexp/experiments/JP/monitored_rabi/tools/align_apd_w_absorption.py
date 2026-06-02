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
                      save_data=False,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.t_imaging_pulse = 50.e-6
        
        self.xvar('make_atoms',[1]*1000)
        
        # self.xvar('amp_imaging',np.linspace(0.1,1.,10))
        self.p.amp_imaging = 0.7

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 1
        
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        if self.p.make_atoms:
            self.prepare_hf_tweezers()
        else:
            delay(1.)
        
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
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