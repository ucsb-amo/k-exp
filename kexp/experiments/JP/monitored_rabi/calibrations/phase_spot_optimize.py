from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class phase_spot(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        # self.xvar('amp_imaging',np.linspace(0.1,1.,10))
        self.p.amp_imaging = 0.25
        self.p.t_imaging_pulse = 5.e-6

        self.xvar('phase_slm_mask', np.linspace(0.42857143-0.03, 0.42857143+.03, 3) * np.pi)
        self.p.phase_slm_mask = 1.05 * np.pi

        # self.xvar('dimension_slm_mask',np.linspace(15.e-6,250.e-6,10))
        # self.p.dimension_slm_mask = 20.e-6
        
        # self.xvar('frequency_detuned_hf_midpoint', self.p.frequency_detuned_hf_midpoint + 50e6 * np.linspace(-1,1,20))
        
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse

        # self.p.v_pd_hf_tweezer_squeeze_power = 8.
        
        self.p.N_repeats = 9

        self.data.apd = self.data.add_data_container(3)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        # self.p.frequency_detuned_hf_midpoint = -518.50e6

        self._idx = 0

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.integrator.init()

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman(phase_mode=0)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        idx0 = 0
        idx1 = 1
        if self._idx == 0:
            # if do pi pulse first, first spin state is now spin down
            self.raman.pulse(self.p.t_raman_pulse)
            self._idx = 1
            idx0 = 1
            idx1 = 0
        else:
            self._idx = 0

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=idx0) # first spin state
        delay(3.e-6)

        self.raman.pulse(self.p.t_raman_pulse)

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=idx1) # second spin state
        delay(10.e-6)

        self.tweezer.off()

        delay(8.e-3)
        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=2) # dark

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