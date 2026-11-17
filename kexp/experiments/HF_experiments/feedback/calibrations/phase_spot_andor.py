from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class phase_spot_andor(EnvExperiment, Base):
    """Phase-spot dispersive signal per spin state, on the Andor.

    Andor version of the APD phase_spot scan. Each shot prepares the atoms in
    ONE state and takes ONE Andor dispersive image of it, in trap, at the
    readout detuning (p.frequency_detuned_hf_midpoint) with the phase spot
    (p.phase_slm_mask, p.dimension_slm_mask):

        t_raman_pulse = 0            -> up (as prepared)
        t_raman_pulse = t_pi         -> down
        t_raman_pulse = t_pi / 2     -> equal superposition (pi/2 from up)

    The state is the inner xvar, so every phase-spot setting gets one shot per
    state per repeat. The image is the usual three frames (atoms in trap,
    light only, dark), so the APD "dark" slot is replaced by the light-only
    and dark frames.
    """

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        # self.xvar('amp_imaging',np.linspace(0.1,1.,10))
        self.p.amp_imaging = 0.25
        self.p.t_imaging_pulse = 5.e-6

        # f = 1.e6
        # df = 0.5e6
        # self.xvar('frequency_detuned_hf_midpoint', -519.5e6 + np.arange(-f,f+df,df))

        # self.p.frequency_detuned_hf_midpoint = -5.0e6

        # self.xvar('phase_slm_mask', 0.387097 * np.pi + np.linspace(-0.2, 0.2, 5) * np.pi)
        # self.xvar('phase_slm_mask', np.linspace(0.26,0.34,11) * np.pi)
        # self.p.phase_slm_mask = 0.387097 * np.pi

        self.xvar('dimension_slm_mask',np.linspace(5.e-6,20.e-6,10))
        self.p.dimension_slm_mask = 20.e-6

        # spin state: up, down, superposition (inner xvar)
        self.xvar('t_raman_pulse', np.array([0.,
                                             self.p.t_raman_pi_pulse,
                                             self.p.t_raman_pi_pulse / 2]))
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse

        self.p.N_repeats = 7

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        # self.p.frequency_detuned_hf_midpoint = -518.50e6

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman(phase_mode=0)

        delay(1.e-3)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        # state preparation: no pulse (up), pi (down) or pi/2 (superposition)
        if self.p.t_raman_pulse > 0.:
            self.raman.pulse(self.p.t_raman_pulse)
        delay(6.e-6)

        # atoms frame in trap; abs_image turns the tweezer off after it,
        # then takes the light-only and dark frames
        self.abs_image()

        delay(10.e-3)

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
