from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu, at_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class rabi_oscillations(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.N_repeats = 3
        self.p.N_pwa_per_shot = 1

        ### Experiment setup
        # self.xvar('t_raman_pulse',np.linspace(0.,8.,9)*1.e-6)
        self.p.t_raman_pulse = 0.

        self.camera_params.amp_imaging = 0.09
        # self.xvar('amp_imaging',np.linspace(0.06,0.1,5))

        ### misc params ###
        self.p.phase_slm_mask = 0.5 * np.pi
        self.p.t_tof = 300.e-6
        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.75]

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,
                                    amp_imaging=self.p.amp_imaging,
                                    pid_bool=True)

        ### prepares the atoms and turns on the PID at self.p.i_spin_mixture ###
        self.prepare_lf_tweezers()
        ### start experiment ###

        self.prep_raman()

        self.raman.on()
        delay(self.p.t_raman_pulse)
        self.raman.off()

        self.tweezer.off()

        delay(self.p.t_tof)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.abs_image()

        self.post_imaging_cleanup()

    @kernel
    def prep_raman(self):
        self.raman.set_transition_frequency(self.p.frequency_raman_transition)
        self.raman.dds_plus.set_dds(amplitude=self.params.amp_raman_plus)
        self.raman.dds_minus.set_dds(amplitude=self.params.amp_raman_minus)
        delay(1.e-3)

    @kernel
    def post_imaging_cleanup(self):
        self.outer_coil.stop_pid()
        self.outer_coil.off()
        self.outer_coil.discharge()
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)