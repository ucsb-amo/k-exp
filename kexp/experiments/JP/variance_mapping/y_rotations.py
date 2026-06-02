from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay
from kexp import Base, img_types, cameras
import numpy as np

class sigma_z(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        self.p.frequency_raman_transition = 119.4636e6 # 182 A -1 0
        self.p.t_raman_pi_pulse = 9.5896e-06 # -1 --> 0
        self.p.frequency_detuned_hf_midpoint = -514.e6 # -1 --> 0
        
        self.p.t_tof = 20.e-6
        self.p.N_repeats = 1

        self.p.amp_imaging = 1.
        self.p.t_img_pulse = 5.e-6

        self.data.apd = self.data.add_data_container(1)

        self.p.t_tweezer_hold = 20.e-3

        self.xvar('switch_axis',[0,1])
        self.p.N_repeats = 10

        self.camera_params.gain = 1.

        self.p.dimension_slm_mask = 20.e-6
        self.p.phase_slm_mask = 0.186 * np.pi

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)
        
        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.integrator.init()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        if self.p.switch_axis:
            self.raman.set_phase(relative_phase=np.pi/4)

        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_img_pulse)
        delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        delay(self.p.t_tof)
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

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)