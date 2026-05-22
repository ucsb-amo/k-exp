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
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
 
        self.xvar('t_raman_pulse', np.linspace(0., 50., 45)*1.e-6)

        self.p.v_pd_hf_tweezer_squeeze_power = 8.

        self.p.amp_imaging = 0.2
        self.p.t_imaging_pulse = 10.e-6

        # self.xvar('t_raman_pulse', self.p.t_raman_pi_pulse * np.array([0.,1.]))

        self.p.t_tweezer_hold = 1.e-3

        self.p.t_tof = 20.e-6
        
        self.p.N_repeats = 3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.integrator.init()

        # self.set_high_field_imaging(i_outer=self.p.i_hf_raman)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(phase_mode=0)

        self.raman.pulse(self.p.t_raman_pulse)
        
        self.integrated_imaging_pulse(self.apd, t=self.p.t_imaging_pulse)

        self.ttl.raman_shutter.off()

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