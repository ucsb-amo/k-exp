from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
import numpy as np

class sigma_z(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        self.p.amp_imaging = 0.23
        self.p.t_pci_pulse = 10.e-6
        
        self.p.t_raman_pulse = 0.
        self.xvar('t_raman_pulse', self.p.t_raman_pi_pulse * np.linspace(0.,1.,2))

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.N_repeats = 10

        self.p.N_pulses = 10

        self.data.apd = self.data.add_data_container(self.p.N_pulses)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)
        
        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.raman.pulse(self.p.t_raman_pulse)

        delay(2.e-6)

        for i in range(self.p.N_pulses):
            self.integrated_imaging_pulse(self.data.apd, t=self.p.t_pci_pulse, idx=i)
            delay(self.p.t_pci_pulse)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)