from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class rabi_chop(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        self.p.amp_imaging = 1.

        # df_per_v_img_amp = 51.96e3 / 1.8
        # self.p.frequency_raman_transition = self.p.frequency_raman_transition + df_per_v_img_amp * self.p.amp_imaging

        # self.xvar('frequency_raman_transition', self.p.frequency_raman_transition + 50.e3 * np.linspace(-1,1,10))

        self.xvar('dummy',[0])

        self.p.t_chopper_imaging_pulse = 1.e-6

        self.camera_params.gain = 1

        self.p.t_raman_pulse = 1.e-6
        self.p.t_tof = 10.e-6
        self.p.N_repeats = 1

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        n = 50
        tr = self.p.t_raman_pulse / n
        ti = self.p.t_chopper_imaging_pulse
        for i in range(n):
            self.raman.pulse(tr)
            self.imaging.pulse(ti)

        delay(10.e-6)

        self.ttl.raman_shutter.off()
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