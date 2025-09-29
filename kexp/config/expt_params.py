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

        # img beam settings
        self.frequency_ao_imaging = 350.00e6
        self.frequency_detuned_imaging = 22.25e6
        self.frequency_detuned_imaging_F1 = 452.e6
        self.beatlock_sign = -1
        self.N_offset_lock_reference_multiplier = 8
        self.frequency_minimum_offset_beatlock = 150.e6
        self.imaging_state = 2.

        # low field imaging settings at i_spin_mixture = 19.48
        # (free space)
        self.frequency_detuned_imaging_m1 = 290.e6
        self.frequency_detuned_imaging_0 = 322.e6
        self.frequency_detuned_imaging_midpoint = 301.3e6
        # self.frequency_detuned_imaging_midpoint = 608.e6

        ## 3D MOT beam imaging settings        
        self.t_repump_flash_imaging = 10.e-6
        self.detune_d2_r_imaging = 0.
        self.amp_d2_r_imaging = 0.065

        self.t_cooler_flash_imaging = 15.e-6
        self.detune_d2_c_imaging = 0.
        self.amp_d2_c_imaging = 0.065
        
        ## 2D MOT imaging settings
        self.amp_d2_2d_c_imaging = 0.188
        self.amp_d2_2d_r_imaging = 0.188
        self.detune_d2_2d_c_imaging = -1.6
        self.detune_d2_2d_r_imaging = -4.4

        # SLM settings
        self.dimension_slm_mask = 30e-6
        self.phase_slm_mask = 2.09 # 0.44 * np.pi
        self.px_slm_phase_mask_position_x = 1119   
        self.px_slm_phase_mask_position_y = 862
        
        # Cooling timing
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
        self.t_gmramp = 6.5e-3
        
        self.t_pump_to_F1 = 150.e-6
        self.t_optical_pumping = 200.e-6
        self.t_optical_pumping_bias_rampup = 2.e-3
        
        self.t_lightsheet_rampup = .12
        self.t_lf_lightsheet_rampdown = .7
        self.t_hf_lightsheet_rampdown = .7
        self.t_hf_lightsheet_rampdown2 = .74
        self.t_lf_lightsheet_rampdown2 = .02
        self.t_lightsheet_rampdown3 = .01
        self.t_lightsheet_load = 10.e-3
        self.t_lightsheet_hold = 40.e-3
        
        self.t_tweezer_ramp = .56
        self.t_tweezer_hold = 5.e-3
        self.t_lf_tweezer_1064_ramp = .28
        self.t_lf_tweezer_1064_rampdown = 200.e-3 
        self.t_lf_tweezer_1064_rampdown2 = 450.e-3   
        self.t_lf_tweezer_1064_rampdown3 = .47
        self.t_hf_tweezer_1064_ramp = .285
        self.t_hf_tweezer_1064_rampdown = 200.e-3 
        self.t_hf_tweezer_1064_rampdown2 = 700.e-3   
        self.t_hf_tweezer_1064_rampdown3 = 470.e-3 
        self.t_tweezer_1064_adiabatic_stretch_ramp = .322
        self.t_tweezer_single_move = 4.e-3
        self.t_tweezer_movement_dt = 10.e-6
        self.t_tweezer_amp_ramp_dt = 10.e-6
        
        self.t_mot_reload = 2.
        self.t_bias_off_wait = 20.e-3
        
        self.t_recover = 40.e-3
        self.t_magtrap_delay = 1.e-3
        self.t_pre_lightsheet_rampup_delay = 0.e-3
        self.t_magtrap = 1.6
        self.t_magtrap_ramp = .4
        # self.t_magtrap_ramp = 4.4
        self.t_magtrap_rampdown = .05
        self.t_yshim_rampdown = 10.e-3
        
        self.t_feshbach_field_rampup = 120.e-3
        self.t_lf_feshbach_field_rampup = 50.e-3
        self.t_feshbach_field_ramp = 12.e-3
        self.t_feshbach_field_ramp2 = 12.e-3
        self.t_feshbach_field_decay = 20.e-3
        self.t_forced_evap_ramp = 2.

        self.t_raman_pi_pulse = 1.2066e-05

        # DAC controlled AO amplitudes
        self.amp_d1_3d_c = 0.3
        self.amp_d1_3d_r = 0.3

        # push beam
        self.detune_push = -1.3
        self.amp_push = 0.188

        #2D MOT
        self.detune_d2v_c_2dmot = -3.43
        self.amp_d2v_c_2dmot = 0.188

        self.detune_d2h_c_2dmot = -1.143
        self.amp_d2h_c_2dmot = 0.188

        self.detune_d2v_r_2dmot = -4.14
        self.amp_d2v_r_2dmot = 0.188

        self.detune_d2h_r_2dmot = -5.571
        self.amp_d2h_r_2dmot = 0.188

        self.v_2d_mot_current = 2.5

        #MOT
        self.detune_d2_c_mot = -2.3
        self.amp_d2_c_mot = 0.188

        self.detune_d2_r_mot = -5.4
        self.amp_d2_r_mot = 0.188

        self.detune_d1_c_mot = 0.
        self.v_pd_d1_c_mot = 5.0

        self.detune_d1_r_mot = 0.
        self.v_pd_d1_r_mot = 5.0

        self.i_mot = 17.6
        self.v_zshim_current = .34
        self.v_xshim_current = .3
        self.v_yshim_current = .82

        #D2 CMOT
        self.detune_d2_c_d2cmot = -0.9
        self.amp_d2_c_d2cmot = 0.14

        self.detune_d2_r_d2cmot = -1.5
        self.amp_d2_r_d2cmot = 0.188

        self.v_d2cmot_current = .98

        #D1 CMOT
        self.detune_d1_c_d1cmot = 7.5 # 12.1
        self.pfrac_d1_c_d1cmot =  0.85 # .57

        self.detune_d2_r_d1cmot = -2.5
        self.amp_d2_r_d1cmot =  0.037 # 0.047

        self.detune_d1_c_sweep_d1cmot_start = 9.
        self.detune_d1_c_sweep_d1cmot_end = 7.
        self.detune_d2_r_sweep_d1cmot_start = -3.
        self.detune_d2_r_sweep_d1cmot_end = -5.
        self.n_d1cmot_detuning_sweep_steps = 200

        self.i_cmot = 20.
        
        #GM
        self.detune_gm = 7.5
        # self.amp_gm = 0.09

        self.v_zshim_current_gm = 0.8
        self.v_xshim_current_gm = 0.5
        self.v_yshim_current_gm = 2.17

        self.detune_d1_c_gm = self.detune_gm
        self.pfrac_d1_c_gm = .99 # there is an ND on this photodiode -- much higher power/volt than the repump
        self.detune_d1_r_gm = self.detune_gm
        self.pfrac_d1_r_gm = .99

        # Discrete GM ramp
        #v_pd values for start and end of ramp
        self.pfrac_c_gmramp_end = .05 #0.01
        self.pfrac_r_gmramp_end = .764# 0.729
        self.n_gmramp_steps = 200

        # mag trap
        self.i_magtrap_init = 84.
        self.i_magtrap_ramp_end = 95.
        # self.n_magtrap_ramp_steps = 1000
        # self.n_magtrap_rampdown_steps = 1000
        
        self.v_zshim_current_magtrap = 0.
        self.v_xshim_current_magtrap = 0.
        self.v_yshim_current_magtrap = 9.9

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
        self.v_pd_lightsheet_rampup_end = 7.3
        self.v_pd_lf_lightsheet_rampdown_end = .71 #4.16
        self.v_pd_hf_lightsheet_rampdown_end = .65 #4.16
        self.v_pd_hf_lightsheet_rampdown2_end = .25
        self.v_pd_lightsheet_rampdown3_end = .0
        self.n_lightsheet_ramp_steps = 1000

        #1064 tweezer
        # self.v_pd_tweezer_1064_pd_minimum = 0.01
        self.amp_tweezer_pid1 = .45
        self.amp_tweezer_pid2 = .45 # brimrose AO
        self.v_pd_tweezer_1064 = 5.

        self.v_pd_lf_tweezer_1064_ramp_end = 9.2
        self.v_pd_lf_tweezer_1064_rampdown_end = .865
        self.v_pd_lf_tweezer_1064_rampdown2_end = .17
        self.v_pd_lf_tweezer_1064_rampdown3_end = 2.

        self.v_pd_hf_tweezer_1064_ramp_end = 9.2
        self.v_pd_hf_tweezer_1064_rampdown_end = 1.13
        self.v_pd_hf_tweezer_1064_rampdown2_end = .155
        self.v_pd_hf_tweezer_1064_rampdown3_end = 2.
        self.n_tweezer_ramp_steps = 1000

        self.v_pd_tweezer_1064_adiabatic_stretch_ramp_end = 9.
        # self.n_tweezer_1064_adiabatic_stretch_ramp_steps = 1000

        self.n_tweezers = 2

        self.frequency_aod_center = 75.e6

        #frequency spacing between each tweezer in the array
        #tweezers uniformly distributed around center frequency of AOD
        # self.frequency_tweezer_spacing = .7e6*2
        self.frequency_tweezer_spacing = 6.e6*2
        # self.frequency_tweezer_list = [73.7e6,76.e6]
        self.frequency_cat_eye_tweezer = 71.3e6
        self.frequency_cateye_threshold = 72.e6
        self.frequency_tweezer_list = [75.4e6]

        # self.frequency_tweezer_auto_compute = False
        # self.amp_tweezer_auto_compute = True
        # self.amp_tweezer_list = [.14,.145]
        # self.amp_tweezer_list = [.4,.4]
        self.amp_tweezer_list = [.15]


        self.frequency_tweezer_list1 = [72250000.,72833333.33333333,73416666.66666667,74000000.]
        self.frequency_tweezer_list2 = [74050000.,74683333.33333333,75316666.66666667,75950000.]

        self.amp_tweezer_list1 = [.25,.25,.25,.25]
        self.amp_tweezer_list2 = [.25,.25,.25,.25]

        # self.v_lf_tweezer_paint_amp_max = .857
        self.v_hf_tweezer_paint_amp_max = 1.

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
        self.frequency_ao_ry_405_switch = 80.0e6
        self.frequency_ao_ry_980_switch = 80.0e6
        self.amp_ao_ry_405_switch = 0.10
        self.amp_ao_ry_980_switch = 0.34

        # raman
        self.frequency_raman_plus = 160.e6 
        self.frequency_raman_minus = 140.e6
        self.amp_raman = .35 # max power & clean pulse shape at 0.35
        self.frequency_raman_zeeman_state_xfer_sweep_center = 40.e6
        self.frequency_raman_zeeman_state_xfer_sweep_fullwidth = 5.e6
        self.n_raman_sweep_steps = 100

        self.frequency_raman_transition = 41.099e6

        # low field evap old
        # self.i_evap1_current = 9.5
        # self.i_evap2_current = 31.3
        # self.i_evap3_current = 25.
        # self.i_evap3_current = 16.4

        # low field evap NEW
        self.i_lf_lightsheet_evap1_current = 12.8

        self.i_lf_tweezer_load_current = 15.4
        self.i_lf_tweezer_evap1_current = 13.9
        self.i_lf_tweezer_evap2_current = 13.2

        self.i_spin_mixture = 19.48

        # high field evap
        self.i_hf_lightsheet_evap1_current = 193.8
        self.i_hf_lightsheet_evap2_current = 193.3

        self.i_hf_tweezer_load_current = 192.8
        self.i_hf_tweezer_evap1_current = 193.0
        self.i_hf_tweezer_evap2_current = 193.15

        # self.i_evap2_current = 198.45
        # self.i_evap3_current = 198.7

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
        