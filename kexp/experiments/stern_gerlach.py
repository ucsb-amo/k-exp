from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu, at_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class rabi_surf(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.N_repeats = 1
        self.p.N_pwa_per_shot = 1

        ### imaging setup ###
        if self.run_info.imaging_type == img_types.DISPERSIVE:
            self.camera_params.exposure_time = 5.e-6
            self.params.t_imaging_pulse = 4.e-6

        # IMAGING FREQUENCIES IN FREE SPACE

        ### Experiment setup

        # self.p.frequency_pci_pulse = 303.4e6
        # self.p.amp_pci_pulse = 0.15

        self.p.t_sg_gradient_ramp = 50.e-3
        self.p.t_sg_gradient_rampdown = 5.e-3
        self.p.t_sg_gradient_hold = 1.e-3
        self.p.i_sg = 5.

        self.xvar('i_sg',np.linspace(0.,10.,5))

        # self.xvar('t_sg_gradient_hold',np.linspace(0.,10.,3)*1.e-3)
        # self.xvar('do_sg',[0,1])
        # self.xvar('dum',[0])

        ### misc params ###
        self.p.phase_slm_mask = 0.5 * np.pi
        self.p.t_tof = 300.e-6
        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]

        self.t = np.zeros(10000,np.int64)
        self.t_idx = 0

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,pid_bool=True)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)

        ### prepares the atoms and turns on the PID at self.p.i_spin_mixture ###
        self.prepare_lf_tweezers()
        ### start experiment ###

        self.prep_stern_gerlach()
        self.init_raman_beams()

        self.pi_pulse()

        self.inner_coil.on()
        self.inner_coil.set_voltage(20.)
        self.inner_coil.ramp_supply(t=self.p.t_sg_gradient_ramp,
                                    i_end=self.p.i_sg)
        self.inner_coil.ramp_supply(t=self.p.t_sg_gradient_ramp,
                                    i_end=0.)
        self.tweezer.off()

        delay(self.p.t_tof)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.abs_image()

    @kernel
    def prep_stern_gerlach(self):
        self.inner_coil.set_voltage(20.)
        self.inner_coil.set_supply(self.p.i_sg)
        
    @kernel
    def stern_gerlach(self):
        self.inner_coil.on()
        delay(self.p.t_sg_gradient_hold)
        self.inner_coil.snap_off()

    @kernel
    def get_time(self):
        self.t[self.t_idx] = now_mu()
        self.t_idx = self.t_idx + 1

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.p.t = self.t
        self.end(expt_filepath)