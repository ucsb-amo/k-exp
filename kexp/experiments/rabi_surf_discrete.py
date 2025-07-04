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

        ### imaging setup ###
        if self.run_info.imaging_type == img_types.DISPERSIVE:
            self.camera_params.exposure_time = 5.e-6
            self.params.t_imaging_pulse = 4.e-6

        ### Experiment setup

        self.p.phase_pci_pulses_relto_raman_drive = 0.
        self.p.N_flops = 1

        self.p.frequency_detuned_pci_during_rabi = self.p.frequency_detuned_imaging_midpoint
        self.p.amp_pci_during_rabi = 0.11
        self.p.t_pci_pulse = 0.6e-6

        self.xvar('t_pulse_interval',np.linspace(0.,10.e-6,5))
        
        # self.xvar('amp_pci_imaging',np.linspace(0.1,0.25,7))
        self.p.amp_pci_imaging = 0.2
        self.p.dt_pwa_interval = 75.e-3

        ### misc params ###
        self.p.t_tof = 500.e-6
        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]

        self.t = np.zeros(10000,np.int64)
        self.t_idx = 0

        self.finish_prepare(shuffle=True)

    @kernel
    def set_up_imaging(self):
        if self.run_info.imaging_type == img_types.DISPERSIVE:
            self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint)
            self.dds.imaging.set_dds(amplitude=self.p.amp_pci_imaging)
        else:
            # self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)
            self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,pid_bool=True)

        # set up PCI detuning for during-flop pulses:
        self.set_imaging_detuning(self.p.frequency_detuned_pci_during_rabi,
                                   amp=self.p.amp_pci_during_rabi)

    @kernel
    def scan_kernel(self):
        self.set_up_imaging()

        ### prepares the atoms and turns on the PID at self.p.i_spin_mixture ###
        self.prepare_lf_tweezers()
        ### start experiment ###

        self.init_raman_beams()

        self.hadamard()
        delay(self.p.t_pulse_interval)
        self.pi_pulse()
        delay(self.p.t_pulse_interval)
        self.hadamard()

        delay(1.e-3)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1,amp=.1)
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,pid_bool=True)
        delay(10.e-3)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def pci_pulse(self):
        self.dds.imaging.on()
        delay(self.p.t_pci_pulse)
        self.dds.imaging.off()

    @kernel
    def get_time(self):
        self.t[self.t_idx] = now_mu()
        self.t_idx = self.t_idx + 1

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.p.t = self.t
        self.end(expt_filepath)