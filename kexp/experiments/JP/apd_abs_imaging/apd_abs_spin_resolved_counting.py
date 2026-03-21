from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu, at_mu

class spin_resolved_counting(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.camera_params.amp_imaging = 0.5

        self.p.t_scope_trig_to_pulse_offset = -30.e-6

        self.p.t_reference_delay_from_first_pulse_mu = 300000

        # self.xvar('t_inter_pulse_time',np.linspace(15.,200.,3)*1.e-6)
        self.p.t_inter_pulse_time = 100.e-6

        self.p.t_imaging_pulse = 5.e-6
        self.p.t_cleanout_pulse = 80.e-6

        self.p.t_tof = 100.e-6
        self.p.N_repeats = 1

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        delay(self.p.t_scope_trig_to_pulse_offset)

        ###

        t = now_mu()
        self.img_pulse()
        delay(self.p.t_inter_pulse_time)

        self.raman.pulse(self.p.t_raman_pi_pulse)
        delay(10.e-6)

        self.img_pulse()
        delay(self.p.t_inter_pulse_time)

        at_mu(t+self.p.t_reference_delay_from_first_pulse_mu)
        self.img_pulse()

        ###

        self.ttl.raman_shutter.off()
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def img_pulse(self):
        self.imaging.pulse(self.p.t_imaging_pulse)

    @kernel
    def cleanout_pulse(self):
        self.imaging.pulse(self.p.t_cleanout_pulse)

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