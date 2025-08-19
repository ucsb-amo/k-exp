from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class measure_rabi_freq(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.amp_raman = .1

        self.p.t_raman_sweep = 500.e-6
        self.p.f_raman_sweep_width = 15.e3
        df = self.p.f_raman_sweep_width/1.5
        self.p.f_raman_sweep_center = 41.10e6
        # self.p.f_raman_sweep_center = 43.e6
        self.xvar('f_raman_sweep_center',
                  self.p.f_raman_sweep_center + np.arange(-50.e3, 50.e3, df))

        self.p.t_tweezer_hold = .1e-3
        self.p.t_tof = 300.e-6
        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)

        self.prepare_lf_tweezers()

        self.init_raman_beams()

        self.ttl.line_trigger.wait_for_line_trigger()

        delay(1.e-3)

        self.raman.sweep(t=self.p.t_raman_sweep,
                         frequency_center=self.p.f_raman_sweep_center,
                         frequency_sweep_fullwidth=self.p.f_raman_sweep_width)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)