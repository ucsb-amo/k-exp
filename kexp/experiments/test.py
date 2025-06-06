from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu

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
        self.p.frequency_detuned_imaging_m1 = 288.e6
        self.p.frequency_detuned_imaging_midpoint = 303.4e6

        self.p.i_spin_mixture = 19.48
        # self.xvar('frequency_detuned_imaging_m1', np.arange(283.,290.,1.)*1.e6) # 2
        # self.xvar('frequency_detuned_imaging_m1', 285.e6 + 20.e6 * np.linspace(-1.,1.,11)) # 2
        # self.p.frequency_detuned_imaging_m1 = 400.e6

        ### Experiment setup

        # self.xvar('t_raman_pulse',np.linspace(0.,3*2*self.p.t_raman_pi_pulse,41))
        # self.p.t_raman_pulse = self.p.t_raman_pi_pulse/2

        self.camera_params.amp_imaging = 0.11

        # t_img_turn_on_delay = 1.57e-6
        # t_list = np.linspace(0.,self.p.t_raman_pi_pulse,11) + t_img_turn_on_delay
        # t_list = t_list[t_list < self.p.t_raman_pi_pulse]
        t_list = np.linspace(-1,1,11) * self.p.t_raman_pi_pulse
        # t_list = np.array([0.,0.5,1.])*self.p.t_raman_pi_pulse
        self.xvar('dt_initial_pci_offset',t_list)
        self.p.dt_initial_pci_offset = 0.
        # self.xvar('phase_pci_pulses_relto_raman_drive',np.linspace(-2*np.pi,2*np.pi,5))
        # self.xvar('dt_offset_pci_pulse_relto_raman_drive',
        #           np.linspace(-self.p.t_raman_pi_pulse,self.p.t_raman_pi_pulse,5))
        self.p.phase_pci_pulses_relto_raman_drive = 0.
        self.p.N_flops = 2

        self.p.frequency_detuned_pci_during_rabi = self.p.frequency_detuned_imaging_midpoint
        self.p.amp_pci_during_rabi = 0.2
        self.p.t_pci_pulse = 0.5e-6
        
        # self.xvar('amp_pci_imaging',np.linspace(0.1,0.25,7))
        self.p.amp_pci_imaging = 0.2
        self.p.dt_pwa_interval = 75.e-3

        # self.xvar('dummy',[0])

        ### misc params ###
        self.p.phase_slm_mask = 0.5 * np.pi
        self.p.t_tof = 300.e-6
        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.75]

        self.t = np.zeros(10000,np.int64)
        self.t_idx = 0

        self.finish_prepare(shuffle=True)

    @kernel
    def pci_pulse(self):
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
        self.prepare_atoms()
        ### start experiment ###

        # set up raman beams
        self.raman.set_transition_frequency(self.p.frequency_raman_transition)
        self.raman.dds_plus.set_dds(amplitude=self.params.amp_raman_plus)
        self.raman.dds_minus.set_dds(amplitude=self.params.amp_raman_minus)

        delay(1.e-3)

        # self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.frequency_raman_transition)

        t_pi = self.p.t_raman_pi_pulse
        dt_initial_pci_offset = self.p.dt_initial_pci_offset
        dt_pci_offset = (self.p.phase_pci_pulses_relto_raman_drive / np.pi) * t_pi
        # dt_pci_offset = self.p.dt_offset_pci_pulse_relto_raman_drive
        # start floppin
        self.raman.on()
        # do pulse train of PCI pulses
        delay(-dt_initial_pci_offset)
        for i in range(self.p.N_flops):
            delay(dt_pci_offset) # offset the start of pulse train
            self.pci_pulse() # pulse (centered on this time, leaves timeline unchanged)
            delay(t_pi) # wait a pi time
            self.pci_pulse() # pulse again
            delay(t_pi-dt_pci_offset)
        self.raman.off()

        # shift imaging back to resonance for absorption imaging
        # wait to make sure imaging beam detuning is updated
        delay(1.e-3)
        self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,
                                    amp_imaging=self.camera_params.amp_imaging,
                                    pid_bool=True)
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
    def prepare_atoms(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=0.,
                        v_xshim_current=0.)

        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_lightsheet_evap1_current,
                             i_end=self.p.i_lf_tweezer_load_current)
        
        #
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_load_current,
                             i_end=self.p.i_lf_tweezer_evap1_current)

        
        # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_lf_tweezer_evap1_current,
                             i_end=self.p.i_lf_tweezer_evap2_current)
        
        # # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        delay(2.e-3)
        # tweezer evap 3 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=20.e-3,
                             i_start=self.p.i_lf_tweezer_evap2_current,
                             i_end=self.p.i_spin_mixture)
        
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid()

        delay(40.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.p.t = self.t
        self.end(expt_filepath)