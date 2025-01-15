import numpy as np
from kexp.config.dds_calibration import DDS_VVA_Calibration
from kexp.util.artiq.async_print import aprint

class ExptParams():
    def __init__(self):

        self.t_rtio = 8.e-9

        self.N_shots = 1
        self.N_repeats = 1
        self.N_img = 1
        self.N_shots_with_repeats = 1
        self.N_pwa_per_shot = 1

        #Magnet
        self.t_keysight_analog_response = 27.2e-3
        self.t_hbridge_switch_delay = 80.e-3
        self.t_contactor_close_delay = 25.e-3
        self.t_contactor_open_delay = 12.e-3

        #Imaging
        self.t_imaging_pulse = 10.e-6
        self.t_light_only_image_delay = 100.e-3
        self.t_dark_image_delay = 25.e-3

        self.frequency_ao_imaging = 350.00e6
        self.frequency_detuned_imaging = 18.0e6
        self.frequency_detuned_imaging_F1 = 410.e6
        self.beatlock_sign = -15
        self.N_offset_lock_reference_multiplier = 8
        self.frequency_minimum_offset_beatlock = 150.e6
        self.imaging_state = 2.
        
        self.t_repump_flash_imaging = 10.e-6
        self.detune_d2_r_imaging = 0.
        self.amp_d2_r_imaging = 0.065

        self.t_cooler_flash_imaging = 15.e-6
        self.detune_d2_c_imaging = 0.
        self.amp_d2_c_imaging = 0.065

        #Cooling timing
        self.t_tof = 20.e-6
        self.t_discharge_igbt = 2.e-3
        self.t_mot_kill = 1.
        self.t_2D_mot_load_delay = 1.
        self.t_mot_load = 1.0
        self.t_d2cmot = 50.e-3
        self.t_d1cmot = 10.e-3
        self.t_magnet_off_pretrigger = 0.e-3
        self.t_shim_change_pretrigger = 0.e-3
        self.t_gm = 3.e-3
        self.t_gmramp = 5.e-3
        self.t_optical_pumping = 200.e-6
        self.t_optical_pumping_bias_rampup = 2.e-3
        self.t_lightsheet_rampup = 1.1
        self.t_lightsheet_rampdown = .4
        self.t_lightsheet_rampdown2 = .061
        self.t_lightsheet_rampdown3 = .01
        self.t_lightsheet_load = 10.e-3
        self.t_lightsheet_hold = 40.e-3
        self.t_tweezer_ramp = .18
        self.t_tweezer_hold = 30.e-3
        self.t_tweezer_1064_ramp = .5
        self.t_tweezer_1064_rampdown = .13
        self.t_tweezer_1064_rampdown2 = .6
        self.t_tweezer_1064_rampdown3 = .18
        self.t_tweezer_1064_adiabatic_stretch_ramp = .322
        self.t_tweezer_single_move = 4.e-3
        self.t_tweezer_movement_dt = 10.e-6
        self.t_tweezer_amp_ramp_dt = 10.e-6
        self.t_mot_reload = 2.
        self.t_bias_off_wait = 20.e-3
        self.t_recover = 40.e-3
        self.t_magtrap_delay = 0.
        self.t_magtrap = 0.
        self.t_magtrap_ramp = 1.
        # self.t_magtrap_ramp = 4.4
        self.t_magtrap_rampdown = .2
        self.t_feshbach_field_rampup = 100.e-3
        self.t_feshbach_field_ramp = 12.e-3
        self.t_feshbach_field_ramp2 = 12.e-3
        self.t_feshbach_field_decay = 20.e-3
        self.t_forced_evap_ramp = 2.

        # DAC controlled AO amplitudes
        self.amp_d1_3d_c = 0.3
        self.amp_d1_3d_r = 0.3

        # push beam
        self.detune_push = -2.4
        self.amp_push = 0.13

        #2D MOT
        self.detune_d2_c_2dmot = -1.2
        self.amp_d2_c_2dmot = 0.188

        self.detune_d2_r_2dmot = -2.4
        self.amp_d2_r_2dmot = 0.188

        self.v_2d_mot_current = 2.11

        #MOT
        self.detune_d2_c_mot = -2.4
        self.amp_d2_c_mot = 0.188

        self.detune_d2_r_mot = -4.2
        self.amp_d2_r_mot = 0.188

        self.detune_d1_c_mot = 0.
        self.v_pd_d1_c_mot = 5.0

        self.detune_d1_r_mot = 0.
        self.v_pd_d1_r_mot = 5.0

        self.i_mot = 20.0
        self.v_zshim_current = 0.13
        self.v_xshim_current = 4.1
        self.v_yshim_current = 7.

        #D2 CMOT
        self.detune_d2_c_d2cmot = -0.9
        self.amp_d2_c_d2cmot = 0.14

        self.detune_d2_r_d2cmot = -1.5
        self.amp_d2_r_d2cmot = 0.188

        self.v_d2cmot_current = .98

        #D1 CMOT
        self.detune_d1_c_d1cmot = 7.5
        self.pfrac_d1_c_d1cmot = .86

        self.detune_d2_r_d1cmot = -3.88
        self.amp_d2_r_d1cmot = 0.065

        self.detune_d1_c_sweep_d1cmot_start = 9.
        self.detune_d1_c_sweep_d1cmot_end = 7.
        self.detune_d2_r_sweep_d1cmot_start = -3.
        self.detune_d2_r_sweep_d1cmot_end = -5.
        self.n_d1cmot_detuning_sweep_steps = 200

        self.i_cmot = 20.
        
        #GM
        self.detune_gm = 7.4
        # self.amp_gm = 0.09

        self.v_zshim_current_gm = 0.83
        self.v_xshim_current_gm = 0.32
        self.v_yshim_current_gm = 2.6

        self.detune_d1_c_gm = self.detune_gm
        self.pfrac_d1_c_gm = .97 # there is an ND on this photodiode -- much higher power/volt than the repump
        self.detune_d1_r_gm = self.detune_gm
        self.pfrac_d1_r_gm = .97

        # Discrete GM ramp
        #v_pd values for start and end of ramp
        self.pfrac_c_gmramp_end = 0.36
        self.pfrac_r_gmramp_end = 0.28
        self.n_gmramp_steps = 200

        # mag trap
        self.i_magtrap_init = 27.
        self.i_magtrap_ramp_end = 95.
        # self.n_magtrap_ramp_steps = 1000
        # self.n_magtrap_rampdown_steps = 1000

        self.v_zshim_current_magtrap_init = 0.
        self.v_zshim_current_magtrap = 0.
        self.v_xshim_current_magtrap = 0.14
        self.v_yshim_current_magtrap = 6.

        #Optical Pumping
        self.detune_optical_pumping_op = 0.0
        self.amp_optical_pumping_op = 0.22
        self.v_anti_zshim_current_op = 0.
        self.v_zshim_current_op = 0.
        self.v_yshim_current_op = 2.0
        self.v_xshim_current_op = 0.17
        self.detune_optical_pumping_r_op = 0.0
        self.amp_optical_pumping_r_op = 0.25

        # ODT
        # self.amp_lightsheet = 0.6
        # self.frequency_ao_lightsheet = 80.e6
        self.v_pd_lightsheet_pd_minimum = 0.046
        self.v_lightsheet_paint_amp_max = 6.0

        self.v_pd_lightsheet = 7.56
        self.v_pd_lightsheet_rampup_start = self.v_pd_lightsheet_pd_minimum
        self.v_pd_lightsheet_rampup_end = 9.99
        self.v_pd_lightsheet_rampdown_end = 8.2 #4.16
        self.v_pd_lightsheet_rampdown2_end = .0
        self.v_pd_lightsheet_rampdown3_end = .0
        self.n_lightsheet_ramp_steps = 1000

        #1064 tweezer
        # self.v_pd_tweezer_1064_pd_minimum = 0.01
        self.amp_tweezer_pid1 = .45
        self.amp_tweezer_pid2 = .45
        self.v_pd_tweezer_1064 = 5.

        self.v_pd_tweezer_1064_ramp_end = 9.
        self.v_pd_tweezer_1064_rampdown_end = .5
        self.v_pd_tweezer_1064_rampdown2_end = .07
        self.v_pd_tweezer_1064_rampdown3_end = .31
        self.n_tweezer_ramp_steps = 1000

        self.v_pd_tweezer_1064_adiabatic_stretch_ramp_end = 9.
        # self.n_tweezer_1064_adiabatic_stretch_ramp_steps = 1000

        self.n_tweezers = 2

        self.frequency_aod_center = 75.e6

        #frequency spacing between each tweezer in the array
        #tweezers uniformly distributed around center frequency of AOD
        # self.frequency_tweezer_spacing = .7e6*2
        self.frequency_tweezer_spacing = 6.e6*2
        self.frequency_tweezer_list = [70.4e6,78.e6]
        self.frequency_cat_eye_tweezer = 71.3e6
        self.frequency_cateye_threshold = 72.e6

        # self.frequency_tweezer_auto_compute = False
        # self.amp_tweezer_auto_compute = True
        self.amp_tweezer_list = [.2,.215]
        # self.amp_tweezer_list = [.4,.4]

        self.v_tweezer_paint_amp_max = -2.7

        # tweezer movement params
        # self.n_steps_tweezer_move = 100
        self.y_tweezer_move = 10.e-6
        self.which_tweezer = 0

        # RF
        self.amp_rf_source = 0.99
        self.n_rf_sweep_steps = 1000

        self.t_rf_sweep_state_prep = 100.e-3
        self.frequency_rf_sweep_state_prep_center = 459.3543e6
        self.frequency_rf_sweep_state_prep_fullwidth = 30.e3
        
        # RF
        self.t_rf_state_xfer_sweep = 60.e-3
        self.frequency_rf_state_xfer_sweep_center = 461.7e6
        self.frequency_rf_state_xfer_sweep_fullwidth = 2.e6

        # feshbach field rampup
        # self.i_feshbach_field_rampup_start = 0.
        self.n_field_ramp_steps = 1000
        # self.n_feshbach_field_rampup_steps = 100
        # self.n_feshbach_field_ramp_steps = 100
        # self.n_feshbach_field_ramp2_steps = 100

        # rydberg
        self.frequency_ao_ry_405 = 250.0e6
        self.frequency_ao_ry_980 = 80.0e6
        self.amp_ao_ry_405 = 0.245
        self.amp_ao_ry_980 = 0.285

        # raman
        self.frequency_raman_plus = 150.e6
        self.frequency_raman_minus = 150.e6
        self.amp_raman_plus = .25
        self.amp_raman_minus = .25
        self.frequency_raman_zeeman_state_xfer_sweep_center = 40.e6
        self.frequency_raman_zeeman_state_xfer_sweep_fullwidth = 5.e6
        self.n_raman_sweep_steps = 100

        # low field evap
        # self.i_evap1_current = 9.5
        # self.i_evap2_current = 31.3
        # self.i_evap3_current = 25.
        # self.i_evap3_current = 16.4

        # high field evap
        self.i_evap1_current = 197.9
        self.i_evap2_current = 198.7
        self.i_evap3_current = 197.6

        # forced evap
        self.i_forced_evap_ramp_init = 0.
        # self.n_forced_evap_ramp_steps = 1000
        self.i_forced_evap_ramp_end = 40.

        self.compute_derived()

    def compute_gmramp_params(self):
        self.pfrac_c_gmramp_start = self.pfrac_d1_c_gm
        self.pfrac_r_gmramp_start = self.pfrac_d1_r_gm

        self.pfrac_c_gmramp_list = np.linspace(self.pfrac_c_gmramp_start, self.pfrac_c_gmramp_end, self.n_gmramp_steps).transpose()
        self.pfrac_r_gmramp_list = np.linspace(self.pfrac_r_gmramp_start, self.pfrac_r_gmramp_end, self.n_gmramp_steps).transpose()

        cal = DDS_VVA_Calibration()
        self.v_pd_c_gmramp_list = cal.power_fraction_to_vva(self.pfrac_c_gmramp_list).transpose()
        self.v_pd_r_gmramp_list = cal.power_fraction_to_vva(self.pfrac_r_gmramp_list).transpose()

        self.dt_gmramp = self.t_gmramp / self.n_gmramp_steps

    def compute_d1cmot_detuning_ramp(self):
        self.detune_d2_r_list_d1cmot = np.linspace(
            self.detune_d2_r_sweep_d1cmot_start,
            self.detune_d2_r_sweep_d1cmot_end,
            self.n_d1cmot_detuning_sweep_steps
        )
        self.detune_d1_c_list_d1cmot = np.linspace(
            self.detune_d1_c_sweep_d1cmot_start,
            self.detune_d1_c_sweep_d1cmot_end,
            self.n_d1cmot_detuning_sweep_steps
        )

    def compute_d1_vvas(self):
        cal = DDS_VVA_Calibration()
        self.v_pd_d1_c_d1cmot = cal.power_fraction_to_vva(self.pfrac_d1_c_d1cmot)
        self.v_pd_d1_c_gm = cal.power_fraction_to_vva(self.pfrac_d1_c_gm)
        self.v_pd_d1_r_gm = cal.power_fraction_to_vva(self.pfrac_d1_r_gm)

    # def compute_tweezer_1064_freqs(self):
    #     if self.frequency_tweezer_auto_compute:
    #         self.frequency_tweezer_list = np.linspace(self.frequency_cat_eye_tweezer,80.e6,self.n_tweezers)
            # self.frequency_tweezer_list = self.frequency_aod_center + (self.n_tweezers-1)/2*self.frequency_tweezer_spacing*np.linspace(-1.,1.,self.n_tweezers)
            # self.frequency_tweezer_list.astype(dtype=float)
            # aprint(self.frequency_tweezer_list.dtype)
            # aprint(type(self.frequency_tweezer_list.dtype))
            # self.frequency_tweezer_list = list(self.frequency_tweezer_list)
        # else:
            # self.frequency_tweezer_list = [self.frequency_aod_center] * self.n_tweezers

    # def compute_tweezer_1064_amps(self):
        # if not self.frequency_tweezer_auto_compute:
        #     if isinstance(self.frequency_tweezer_list,float):
        #         self.n_tweezers = 1
        #     else:
        #         self.n_tweezers = len(self.frequency_tweezer_list)
        # if self.amp_tweezer_auto_compute:
        #     self.amp_tweezer_list = np.ones(self.n_tweezers) / self.n_tweezers
        # else:
        #     self.amp_tweezer_list = self.amp_tweezer_list

    def compute_tweezer_1064_phases(self):
        self.phase_tweezer_array = np.zeros([len(self.amp_tweezer_list)])
        for tweezer_idx in range(len(self.amp_tweezer_list)):
            if tweezer_idx == 0:
                self.phase_tweezer_array[0] =  360.
            else:
                phase_ij = 0
                for j in range(1,tweezer_idx):
                    phase_ij = phase_ij + 2*np.pi*(tweezer_idx - j)*self.amp_tweezer_list[tweezer_idx]
                phase_i = (phase_ij % 2*np.pi) * 360
                self.phase_tweezer_array[tweezer_idx] = phase_i

    def compute_derived(self):
        '''loop through methods (except built in ones) and compute all derived quantities'''
        methods = [m for m in dir(self) if not m.startswith('__') and callable(getattr(self,m)) and not m == 'compute_derived']
        for m in methods:
            getattr(self,m)()
        