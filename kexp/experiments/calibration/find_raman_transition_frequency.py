from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np

from waxx.util.artiq.async_print import aprint

from artiq.language.core import now_mu, at_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class rabi_surf(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        ### Experiment setup

        self.p.f_raman_sweep_width = 10.e3

        sweep_scan_width = 80.e3
        self.xvar('f_raman_sweep_center',
                  41.26e6 + np.arange(-sweep_scan_width, sweep_scan_width, self.p.f_raman_sweep_width))

        self.p.t_raman_sweep = 1000.e-6

        self.p.amp_raman = 0.19

        ### misc params ###
        self.p.t_tof = 250.e-6

        self.p.amp_imaging = .4
        self.camera_params.exposure_time = 20.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time
        self.p.N_repeats = 1
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        ### prepares the atoms and turns on the PID at self.p.i_spin_mixture ###
        self.prepare_lf_tweezers()

        ### start experiment ###

        self.init_raman_beams()

        self.raman.sweep(t=self.p.t_raman_sweep,
                         frequency_center=self.p.f_raman_sweep_center,
                         frequency_sweep_fullwidth=self.p.f_raman_sweep_width,
                         n_steps=50)

        # delay(self.p.t_raman_sweep)

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