from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='andor',save_data=False)

        # self.xvar('f_raman_sweep_width',np.linspace(10.e3,60.e3,6))
        self.p.f_raman_sweep_width = 2.e6

        self.xvar('f_raman_sweep_center',np.arange(38.e6, 42.e6, self.p.f_raman_sweep_width))
        # self.xvar('f_raman_sweep_center',np.linspace(41.0e6, 41.16e6, self.p.f_raman_sweep_width))
        self.p.f_raman_sweep_center = 41.11e6
        # self.p.f_raman_sweep_center = self.p.frequency_raman_transition

        # self.xvar('t_raman_sweep',np.linspace(200.e-6,3.e-3,10))
        self.p.t_raman_sweep = 5.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.init_raman_beams()

        delay(1.e-3)
        self.raman.sweep(t=self.p.t_raman_sweep,
                         frequency_center=self.p.f_raman_sweep_center,
                         frequency_sweep_fullwidth=self.p.f_raman_sweep_width)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)