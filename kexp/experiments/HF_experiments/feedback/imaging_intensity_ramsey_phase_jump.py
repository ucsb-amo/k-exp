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

        # self.xvar('amp_imaging', np.linspace(0.2, 1.5, 6))
        self.xvar('with_imaging', [0,1])
        self.xvar('relative_phase', np.linspace(0., 3*np.pi, 20))

        self.p.t_ramsey = 5.e-6
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 2

        # self.xvar('amp_imaging',np.linspace(0.1,.4,10))
        self.p.amp_imaging = .2
        
        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 100.e-6
        self.p.t_mot_load = 1.
        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)
        
    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman()

        self.raman.set(t_phase_origin_mu=now_mu())

        self.raman.pulse(self.p.t_raman_pulse)

        if self.p.with_imaging:
            self.imaging.on()
            delay(self.p.t_ramsey)
            self.imaging.off()
        else:
            delay(self.p.t_ramsey)

        self.raman.set(relative_phase=self.p.relative_phase)
        self.raman.pulse(self.p.t_raman_pulse)

        self.ttl.raman_shutter.off()

        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(.2)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)