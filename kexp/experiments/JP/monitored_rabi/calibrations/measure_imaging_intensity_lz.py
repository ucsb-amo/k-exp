from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class ramsey(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.p.frequency_shift_per_imaging_amp_estimation = 161.e3 # Hz/V

        self.p.fraction_power_raman = 0.2
        self.p.t_raman_sweep = 2.e-3
        self.p.frequency_raman_sweep_width = 10.e3
        df = self.p.frequency_raman_sweep_width

        self.p.amp_imaging = 0.5
        self.p.frequency_raman_transition_detuning = 0.

        # self.xvar('amp_imaging',np.linspace(0.1,0.5,10))
        self.xvar('frequency_raman_transition_detuning', np.arange(-50.e3,50.e3+df,df))

        self.p.t_tof = 100.e-6
        self.p.N_repeats = 1

        self.data.frequency_raman_transition = self.data.add_data_container()

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging_midpoint)
        if self.p.amp_imaging != 0.:
            self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()

        f0 = self.p.frequency_raman_transition
        df_per_img_v = self.p.frequency_shift_per_imaging_amp_estimation
        f = f0 + df_per_img_v * self.p.amp_imaging + self.p.frequency_raman_transition_detuning
        
        self.prep_raman(frequency_raman=f)

        if self.p.amp_imaging != 0.:
            self.imaging.on()

        self.raman.sweep(t=self.p.t_raman_sweep,
                         frequency_center=f,
                         frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
                         n_steps=100)

        self.imaging.off()

        self.ttl.raman_shutter.off()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.data.frequency_raman_transition.put_data(f)
        self.core.break_realtime()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)