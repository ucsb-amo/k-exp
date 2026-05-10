from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu, at_mu

from kexp.util.artiq.async_print import aprint

class rabi_oscillation(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        self.p.amp_imaging_pci = 0.2
        # self.xvar('amp_imaging_pci',np.linspace(0.1,0.5,30))

        self.p.t_imaging_pulse = 5.e-6

        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 3

        self.xvar('t_raman_pulse', self.p.t_raman_pulse * np.linspace(.9,1.1,7))

        self.p.phase_rabi_surf_train_radians = 0

        self.p.time_for_bye = 10.e-6

        self.camera_params.gain = 0

        self.p.t_tof = 100.e-6
        self.p.N_repeats = 3

        self.p.N_pulses = 20
        self.data.apd = self.data.add_data_container(self.p.N_pulses)
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)

        self.data.t = self.data.add_data_container(self.p.N_pulses)


        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.integrator.init()

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging_pci)

        self.prepare_hf_tweezers()
        self.prep_raman()

        t_offset = self.p.phase_rabi_surf_train_radians * (self.p.t_raman_pi_pulse / np.pi)
        self.raman.pulse(t_offset)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        delay(5.e-6)

        i = 0
        t = now_mu()
        for i in range(self.p.N_pulses):

            self.integrated_imaging_pulse(self.data.apd, self.p.t_imaging_pulse, i)

            delay(self.p.time_for_bye)

            ti = now_mu() - t
            self.data.t.put_data(ti*1.e-9, i)

            for i in range(6):
                self.raman.pulse(self.p.t_raman_pulse)
                delay(200.e-9)

            delay(5.e-6)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(10.e-3)

        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep([0])
        self.core.break_realtime()
        delay(150.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)