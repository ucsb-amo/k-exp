from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class rabi_oscillation(EnvExperiment, Base):
    kernel_invariants = {
                        "m",
                        "dt",
                        "N_pulses",
                        "N_photons_per_shot",
                        "v_apd_all_up",
                        "v_apd_all_down",
                        "v_range"}

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        self.m = 21
        self.P0 = np.ones(self.m, dtype=float)
        self.P0 = self.P0 / np.sum(self.P0)

        self.P1 = np.zeros((self.m, 2), dtype=complex)

        omega0 = 2*np.pi*self.p.frequency_raman_transition
        Omega = 2*np.pi*80.e3
        offset = 5
        self.omega0_list = omega0 + 2*offset*Omega*np.linspace(-1,1,self.m)

        self.dt = 2.e-6
        self.N_pulses = 8 # nu

        self.N_photons_per_shot = 100

        self.v_apd_all_up = -1.5
        self.v_apd_all_down = -1.0
        self.v_range = self.v_apd_all_up - self.v_apd_all_down

        self.data.apd = self.data.add_data_container(100)
        self.idx = 0
        
        self.finish_prepare()

    @kernel
    def feedback_experiment(self):
        pass

    @kernel
    def scan_kernel(self):
        self.integrator.init()
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.feedback_experiment()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def generate_posterior(self):
        pass

    @kernel
    def convert_measurement(self, v_apd):
        return (v_apd - self.v_apd_all_down) / self.v_range
    
    @kernel
    def measurement(self):
        idx = self.idx
        self.integrated_imaging_pulse(self.data.apd, t=self.dt, idx=self.idx)
        self.idx = self.idx + 1
        return self.convert_measurement(self.data.apd[idx])

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)