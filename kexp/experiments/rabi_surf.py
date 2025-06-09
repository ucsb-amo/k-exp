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
        
        self.p.N_repeats = 5
        self.p.N_pwa_per_shot = 1

        ### imaging setup ###
        if self.run_info.imaging_type == img_types.DISPERSIVE:
            self.camera_params.exposure_time = 5.e-6
            self.params.t_imaging_pulse = 4.e-6

        # IMAGING FREQUENCIES IN FREE SPACE
        self.p.frequency_detuned_imaging_m1 = 288.e6
        # self.p.frequency_detuned_imaging_midpoint = 303.4e6
        self.p.frequency_detuned_imaging_midpoint = 615.e6
        self.p.frequency_detuned_imaging_0 = 318.e6

        self.p.i_spin_mixture = 19.48
        # self.xvar('frequency_detuned_imaging_m1', np.arange(283.,290.,1.)*1.e6) # 2
        # self.xvar('frequency_detuned_imaging_m1', 285.e6 + 20.e6 * np.linspace(-1.,1.,11)) # 2
        # self.p.frequency_detuned_imaging_m1 = 400.e6

        ### Experiment setup
        self.camera_params.amp_imaging = 0.11

        # t_list = np.linspace(-1,1,9) * self.p.t_raman_pi_pulse
        # self.xvar('dt_initial_pci_offset',t_list)
        self.p.dt_initial_pci_offset = 0.

        self.xvar('phase_pci_pulses_relto_raman_drive',np.linspace(0.,3.14,20))
        self.p.phase_pci_pulses_relto_raman_drive = 0.
        self.p.N_flops = 3

        # rabi_flop_sampling_interval = 1/4 # in units of pi times
        # self.xvar('t_raman_pulse',self.p.t_raman_pi_pulse*np.arange(0.,
        #                                                             2*self.p.N_flops + rabi_flop_sampling_interval,
        #                                                             rabi_flop_sampling_interval))
        # self.xvar('t_raman_pulse',self.p.t_raman_pi_pulse*np.linspace(0.,3.,20))
        # self.p.t_raman_pulse = self.p.t_raman_pi_pulse/2 + self.p.t_raman_pi_pulse * 2 * np.pi
        # self.p.t_raman_pulse = 0.

        self.p.frequency_detuned_pci_during_rabi = self.p.frequency_detuned_imaging_midpoint
        # self.xvar('amp_pci_during_rabi', np.linspace(.08,.21,10))
        self.p.amp_pci_during_rabi = 0.11
        self.p.t_pci_pulse = 0.6e-6

        self.p.t_raman_pi_pulse = 3.8e-6
        
        # self.xvar('amp_pci_imaging',np.linspace(0.1,0.25,7))
        self.p.amp_pci_imaging = 0.2
        self.p.dt_pwa_interval = 75.e-3

        ### misc params ###
        self.p.phase_slm_mask = 0.5 * np.pi
        self.p.t_tof = 500.e-6
        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]

        self.t = np.zeros(10000,np.int64)
        self.t_idx = 0

        self.finish_prepare(shuffle=True)

    @kernel
    def pci_pulse(self):
        self.get_time()
        delay(-self.p.t_pci_pulse/2)
        self.dds.imaging.on()
        delay(self.p.t_pci_pulse)
        self.dds.imaging.off()
        delay(-self.p.t_pci_pulse/2)

    @kernel
    def get_time(self):
        self.t[self.t_idx] = now_mu()
        self.t_idx = self.t_idx + 1

    @kernel
    def scan_kernel(self):
        if self.run_info.imaging_type == img_types.DISPERSIVE:
            self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint)
            self.dds.imaging.set_dds(amplitude=self.p.amp_pci_imaging)
        else:
            # self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)
            self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,pid_bool=True)

        # set up PCI detuning for during-flop pulses:
        self.set_imaging_detuning(self.p.frequency_detuned_pci_during_rabi,
                                   amp=self.p.amp_pci_during_rabi)

        ### prepares the atoms and turns on the PID at self.p.i_spin_mixture ###
        self.prepare_lf_tweezers()
        ### start experiment ###

        # set up raman beams
        self.raman.set_transition_frequency(self.p.frequency_raman_transition)
        self.raman.dds_plus.set_dds(amplitude=self.params.amp_raman_plus)
        self.raman.dds_minus.set_dds(amplitude=self.params.amp_raman_minus)

        # delay(1.e-3)

        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.frequency_raman_transition)

        t_pi = self.p.t_raman_pi_pulse
        dt_initial_pci_offset = self.p.dt_initial_pci_offset
        dt_pci_offset = (self.p.phase_pci_pulses_relto_raman_drive / np.pi) * t_pi
        
        # breaks at self.p.t_raman_pulse
        # tf = now_mu() + self.core.seconds_to_mu(self.p.t_raman_pulse)

        # does self.p.N_flops full periods:
        tf = now_mu() + self.core.seconds_to_mu(self.p.N_flops * 2 * t_pi)

        # start floppin
        self.raman.on()
        delay(t_pi)
        # self.raman.off()

        # delay(-dt_initial_pci_offset)

        for i in range(self.p.N_flops):

            delay(dt_pci_offset) # offset the start of pulse train
            if now_mu() > tf:
                break

            self.pci_pulse() # pulse (centered on this time, leaves timeline unchanged)

            delay(t_pi) # wait a pi time
            if now_mu() > tf:
                break

            self.pci_pulse() # pulse again

            delay(t_pi-dt_pci_offset)
            if now_mu() > tf:
                break

        at_mu(tf)
        # delay(dt_initial_pci_offset)

        self.raman.off()

        # shift imaging back to resonance for absorption imaging
        # wait to make sure imaging beam detuning is updated
        delay(1.e-3)
        # self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,
        #                             amp_imaging=self.camera_params.amp_imaging,
        #                             pid_bool=True)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_0,
                                   amp=.1)
        delay(10.e-3)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.post_imaging_cleanup()

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
        self.p.t = self.t
        self.end(expt_filepath)