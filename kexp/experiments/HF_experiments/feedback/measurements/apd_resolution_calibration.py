from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
import numpy as np
from numpy import int64

class sigma_z(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        self.p.amp_imaging = 0.2
        self.p.t_pci_pulse = 5.e-6

        self.p.t_raman_pulse = 0.
        self.p.t_raman_pulse_offset = 127.e-9
        self.xvar('t_raman_pulse', self.p.t_raman_pi_pulse * np.linspace(0.,1.,3))

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.N_repeats = 25

        self.data.apd = self.data.add_data_container(2)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        if self.p.t_raman_pulse > 0:
            self.p.t_raman_pulse += self.p.t_raman_pulse_offset
        self.raman.pulse(self.p.t_raman_pulse)

        delay(50.e-6)

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_pci_pulse, idx=0)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(100.e-3)

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_pci_pulse, idx=1)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, restart_monitor=False)