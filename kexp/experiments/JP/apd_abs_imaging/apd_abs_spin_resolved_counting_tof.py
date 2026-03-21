from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu, at_mu

class spin_resolved_counting_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.p.amp_imaging = 0.3
        # self.xvar('amp_imaging',np.linspace(0.05,0.5,5))

        self.p.t_tof_apd_abs = 250.e-6

        self.p.t_imaging_pulse = 5.e-6
        # self.p.t_raman_pulse = self.p.t_raman_pi_pulse/2
        self.xvar('t_raman_pulse',self.p.t_raman_pi_pulse*np.linspace(0.8,1.0,5))

        # self.xvar('t_tof_apd_abs',np.linspace(0.,300.,5)*1.e-6)
        self.p.N_repeats = 12

        self.p.t_tweezer_hold = 1.e-3

        self.camera_params.gain = 0

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.data.apd = self.data.add_data_container(4)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.raman.pulse(self.p.t_raman_pulse)
        delay(self.p.t_tweezer_hold)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        delay(5.e-6)

        ###

        self.tof_apd_abs_image()

        ###

        self.ttl.raman_shutter.off()

        delay(10.e-3)
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
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)