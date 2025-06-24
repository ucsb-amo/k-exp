from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu, at_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class rabi_surf(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.N_repeats = 1
        self.p.N_pwa_per_shot = 1

        ### Experiment setup

        self.p.f_raman_sweep_width = 50.e3

        sweep_scan_width = 100.e3
        self.xvar('f_raman_sweep_center',
                  41.294e6 + np.arange(-sweep_scan_width, sweep_scan_width, self.p.f_raman_sweep_width/2))

        self.p.t_raman_sweep = 200.e-6

        ### misc params ###
        self.p.t_tof = 300.e-6
        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)

        ### prepares the atoms and turns on the PID at self.p.i_spin_mixture ###
        self.prepare_lf_tweezers()
        ### start experiment ###

        self.init_raman_beams()

        self.raman.sweep(t=self.p.t_raman_sweep,
                         frequency_center=self.p.f_raman_sweep_center,
                         frequency_sweep_fullwidth=self.p.f_raman_sweep_width,
                         n_steps=50)

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