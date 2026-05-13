from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        self.xvar('frequency_raman_transition',119.4639e6 + np.linspace(-1.e3,1.e3,11))

        self.xvar('t_ramsey', np.linspace(10.e-6, 750.e-6, 7))
 
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 2 # -1 --> 0

        self.p.t_tweezer_hold = .01e-3

        self.p.t_tof = 90.e-6
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)

        self.raman.init(frequency_transition = self.p.frequency_raman_transition, 
                        fraction_power = self.params.fraction_power_raman)
        
        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)

        self.raman.pulse(self.p.t_raman_pulse)

        delay(self.p.t_ramsey)

        self.raman.pulse(self.p.t_raman_pulse)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        self.outer_coil.stop_pid()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)