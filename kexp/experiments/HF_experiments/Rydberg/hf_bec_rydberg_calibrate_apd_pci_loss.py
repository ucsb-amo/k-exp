
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel, now_mu
from kexp import Base, img_types, cameras

class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.DISPERSIVE)
        
         # self.xvar('compress',[0,1])
        self.p.compress = 0

        # self.xvar('t_tweezer_hold', [0., 50.e-3, 100.e-3])
        self.p.t_tweezer_hold = 100.e-3

        self.p.amp_imaging = 0.25

        self.p.t_imaging_pulse = 10.e-6

        self.p.N_repeats = 25

        n_max_pulses = 20
        # self.xvar('N_pulses',np.arange(n_max_pulses + 1).astype(int))
        self.p.N_pulses = n_max_pulses

        self.data.apd = self.data.add_data_container(n_max_pulses, float)
        self.data.t_pulse = self.data.add_data_container(n_max_pulses, float)
        self.data.apd_no_atoms = self.data.add_data_container(1, float)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        if self.p.compress:
            self.prepare_hf_tweezers(squeeze=True)
        else:
            self.prepare_hf_tweezers(squeeze=False, do_tweezer_evap_3=True, do_tweezer_evap_2=True)
        
        delay(self.p.t_tweezer_hold)

        delay(100.e-6)

        T = self.p.t_tweezer_hold
        dt = T / self.p.N_pulses

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        t = 0.
        t0 = now_mu()

        for i in range(self.p.N_pulses):
            t = (now_mu() - t0)*1.e-9
            self.integrated_imaging_pulse(self.data.apd,t=self.p.t_imaging_pulse, idx=i)
            self.data.t_pulse.put_data(t, i=i)
            delay(dt)

        self.tweezer.off()
        self.outer_coil.off()

        delay(10.e-3)
        self.integrated_imaging_pulse(self.data.apd_no_atoms, t=self.p.t_imaging_pulse)

        delay(10.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
