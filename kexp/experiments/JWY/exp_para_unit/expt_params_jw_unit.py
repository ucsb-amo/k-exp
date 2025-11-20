import numpy as np
from kexp.config.dds_calibration import DDS_VVA_Calibration

class ExptParams():
    def __init__(self):

        self.t_rtio = 8.e-9  # ns

        self.N_shots = 1  # count
        self.N_repeats = 1  # count
        self.N_img = 1  # count
        self.N_shots_with_repeats = 1  # count
        self.N_pwa_per_shot = 1  # count

        # Magnet
        self.t_keysight_analog_response = 27.2e-3  # ms
        self.t_hbridge_switch_delay = 80.e-3  # ms
        self.t_contactor_close_delay = 25.e-3  # ms
        self.t_contactor_open_delay = 12.e-3  # ms

        # Imaging
        self.t_imaging_pulse = 10.e-6  # us

        # img beam settings
        self.frequency_detuned_imaging = 22.25e6  # MHz
        self.frequency_detuned_imaging_F1 = 452.e6  # MHz
        self.beatlock_sign = -1  # unitless
        self.N_offset_lock_reference_multiplier = 8  # count
        self.frequency_minimum_offset_beatlock = 150.e6  # MHz
        self.imaging_state = 2.  # state index

        # low field imaging settings at i_spin_mixture = 19.48
        # (free space)
        self.frequency_detuned_imaging_m1 = 290.e6  # MHz
        self.frequency_detuned_imaging_0 = 322.e6  # MHz
        self.frequency_detuned_imaging_midpoint = 301.3e6  # MHz
        # self.frequency_detuned_imaging_midpoint = 608.e6

        ## 3D MOT beam imaging settings        
        self.t_repump_flash_imaging = 10.e-6  # us
        self.detune_d2_r_imaging = 0.  # Gamma (linewidths)
        self.amp_d2_r_imaging = 0.065  # amplitude (0–1)

        self.t_cooler_flash_imaging = 15.e-6  # us
        self.detune_d2_c_imaging = 0.  # Gamma (linewidths)
        self.amp_d2_c_imaging = 0.065  # amplitude (0–1)
        
        ## 2D MOT imaging settings
        self.amp_d2_2d_c_imaging = 0.188  # amplitude (0–1)
        self.amp_d2_2d_r_imaging = 0.188  # amplitude (0–1)
        self.detune_d2_2d_c_imaging = -1.6  # Gamma (linewidths)
        self.detune_d2_2d_r_imaging = -4.4  # Gamma (linewidths)

        # SLM settings
        self.dimension_slm_mask = 100e-6  # m
        self.phase_slm_mask = 2.09  # rad
        self.px_slm_phase_mask_position_x = 1034  # px
        self.px_slm_phase_mask_position_y = 835  # px
        
        # Cooling timing
        self.t_tof = 20.e-6  # us
        self.t_discharge_igbt = 2.e-3  # ms
        
        self.t_mot_kill = 1.  # s
        self.t_2D_mot_load_delay = 1.  # s
        self.t_mot_load = 1.0  # s
        
        self.t_d2cmot = 50.e-3  # ms
        self.t_d1cmot = 10.e-3  # ms
        
        self.t_magnet_off_pretrigger = 0.e-3  # ms
        self.t_shim_change_pretrigger = 0.e-3  # ms
       
        self.t_gm = 3.e-3  # ms
        self.t_gmramp = 6.5e-3  # ms
        
        self.t_pump_to_F1 = 150.e-6  # us
        self.t_optical_pumping = 200.e-6  # us
        self.t_optical_pumping_bias_rampup = 2.e-3  # ms
        
        self.t_lightsheet_rampup = .16  # s
        self.t_lf_lightsheet_rampdown = 1.13  # s
        self.t_hf_lightsheet_rampdown = 1.13  # s
        self.t_hf_lightsheet_rampdown2 = .74  # s
        self.t_lf_lightsheet_rampdown2 = .02  # s
        self.t_lightsheet_rampdown3 = .01  # s
        self.t_lightsheet_load = 10.e-3  # ms
        self.t_lightsheet_hold = 40.e-3  # ms
        
        self.t_tweezer_ramp = .56  # s
        self.t_tweezer_hold = 5.e-3  # ms
        self.t_lf_tweezer_1064_ramp = .28  # s
        self.t_lf_tweezer_1064_rampdown = 140.e-3  # ms 
        self.t_lf_tweezer_1064_rampdown2 = 450.e-3  # ms   
        self.t_lf_tweezer_1064_rampdown3 = .47  # s
        self.t_hf_tweezer_1064_ramp = .285  # s
        self.t_hf_tweezer_1064_rampdown = 200.e-3  # ms 
        self.t_hf_tweezer_1064_rampdown2 = 700.e-3  # ms   
        self.t_hf_tweezer_1064_rampdown3 = 470.e-3  # ms 
        self.t_tweezer_1064_adiabatic_stretch_ramp = .322  # s
        self.t_tweezer_single_move = 4.e-3  # ms
        self.t_tweezer_movement_dt = 10.e-6  # us
        self.t_tweezer_amp_ramp_dt = 10.e-6  # us

        self.t_ramp_down_painting_amp = 15.e-3  # ms
        
        self.t_mot_reload = 2.  # s
        self.t_bias_off_wait = 20.e-3  # ms
        
        self.t_recover = 40.e-3  # ms
        self.t_magtrap_delay = 1.e-3  # ms
        self.t_pre_lightsheet_rampup_delay = 0.e-3  # ms
        self.t_magtrap = 1.6  # s
        self.t_magtrap_ramp = .4  # s
        # self.t_magtrap_ramp = 4.4
        self.t_magtrap_rampdown = .05  # s
        self.t_yshim_rampdown = 10.e-3  # ms
        
        self.t_feshbach_field_rampup = 120.e-3  # ms
        self.t_lf_feshbach_field_rampup = 50.e-3  # ms
        self.t_feshbach_field_ramp = 12.e-3  # ms
        self.t_feshbach_field_ramp2 = 12.e-3  # ms
        self.t_feshbach_field_decay = 20.e-3  # ms
        self.t_forced_evap_ramp = 2.  # s

        self.t_feshbach_field_ramp_special = 20.e-3  # ms

        self.t_raman_pi_pulse = 1.2392e-05  # us (≈12.4 us)

        # DAC controlled AO amplitudes
        self.amp_d1_3d_c = 0.3  # amplitude (0–1)
        self.amp_d1_3d_r = 0.3  # amplitude (0–1)

        # push beam
        self.detune_push = -1.3  # Gamma (linewidths)
        self.amp_push = 0.188  # amplitude (0–1)

        # 2D MOT
        self.detune_d2v_c_2dmot = -3.43  # Gamma (linewidths)
        self.amp_d2v_c_2dmot = 0.188  # amplitude (0–1)

        self.detune_d2h_c_2dmot = -1.71  # Gamma (linewidths)
        self.amp_d2h_c_2dmot = 0.188  # amplitude (0–1)

        self.detune_d2v_r_2dmot = -3.6  # Gamma (linewidths)
        self.amp_d2v_r_2dmot = 0.188  # amplitude (0–1)

        self.detune_d2h_r_2dmot = -6.  # Gamma (linewidths)
        self.amp_d2h_r_2dmot = 0.188  # amplitude (0–1)

        self.v_2d_mot_current = 2.3  # V

        # MOT
        self.detune_d2_c_mot = -2.43  # Gamma (linewidths)
        self.amp_d2_c_mot = 0.188  # amplitude (0–1)

        self.detune_d2_r_mot = -5.3  # Gamma (linewidths)
        self.amp_d2_r_mot = 0.188  # amplitude (0–1)

        self.detune_d1_c_mot = 0.  # Gamma (linewidths)
        self.v_pd_d1_c_mot = 5.0  # V

        self.detune_d1_r_mot = 0.  # Gamma (linewidths)
        self.v_pd_d1_r_mot = 5.0  # V

        self.i_mot = 17.8  # A
        self.v_zshim_current = .48  # V
        self.v_xshim_current = .9  # V
        self.v_yshim_current = 1.7  # V

        # D2 CMOT
        self.detune_d2_c_d2cmot = -0.9  # Gamma (linewidths)
        self.amp_d2_c_d2cmot = 0.14  # amplitude (0–1)

        self.detune_d2_r_d2cmot = -1.5  # Gamma (linewidths)
        self.amp_d2_r_d2cmot = 0.188  # amplitude (0–1)

        self.v_d2cmot_current = .98  # V

        # D1 CMOT
        self.detune_d1_c_d1cmot = 9.5  # Gamma (linewidths)  # 12.1
        self.pfrac_d1_c_d1cmot = 0.85  # power fraction  # .57

        self.detune_d2_r_d1cmot = -3.29  # Gamma (linewidths)
        self.amp_d2_r_d1cmot = 0.037  # amplitude (0–1)  # 0.047

        self.detune_d1_c_sweep_d1cmot_start = 9.  # Gamma (linewidths)
        self.detune_d1_c_sweep_d1cmot_end = 7.  # Gamma (linewidths)
        self.detune_d2_r_sweep_d1cmot_start = -3.  # Gamma (linewidths)
        self.detune_d2_r_sweep_d1cmot_end = -5.  # Gamma (linewidths)
        self.n_d1cmot_detuning_sweep_steps = 200  # steps

        self.i_cmot = 20.  # A
        
        # GM
        self.detune_gm = 7.37  # Gamma (linewidths)
        # self.amp_gm = 0.09

        self.v_zshim_current_gm = 0.7  # V
        self.v_xshim_current_gm = 0.4  # V
        self.v_yshim_current_gm = 2.  # V

        self.detune_d1_c_gm = self.detune_gm  # Gamma (linewidths)
        self.pfrac_d1_c_gm = .736  # power fraction (0–1), ND on PD
        self.detune_d1_r_gm = self.detune_gm  # Gamma (linewidths)
        self.pfrac_d1_r_gm = .99  # power fraction (0–1)

        # Discrete GM ramp
        # v_pd values for start and end of ramp
        self.pfrac_c_gmramp_end = .05  # power fraction
        self.pfrac_r_gmramp_end = .764  # power fraction
        self.n_gmramp_steps = 200  # steps

        # mag trap
        self.i_magtrap_init = 95.  # A
        self.i_magtrap_ramp_end = 95.  # A
        # self.n_magtrap_ramp_steps = 1000
        # self.n_magtrap_rampdown_steps = 1000
        
        self.v_zshim_current_magtrap = 0.  # V
        self.v_xshim_current_magtrap = 0.  # V
        self.v_yshim_current_magtrap = 8.  # V

        # Optical Pumping
        self.detune_optical_pumping_op = 0.0  # Gamma (linewidths)
        self.amp_optical_pumping_op = 0.22  # amplitude (0–1)
        self.v_anti_zshim_current_op = 0.  # V
        self.v_zshim_current_op = 0.  # V
        self.v_yshim_current_op = 2.0  # V
        self.v_xshim_current_op = 0.17  # V
        self.detune_optical_pumping_r_op = 0.0  # Gamma (linewidths)
        self.amp_optical_pumping_r_op = 0.25  # amplitude (0–1)

        # ODT
        # self.amp_lightsheet = 0.6
        # self.frequency_ao_lightsheet = 80.e6
        self.v_pd_lightsheet_pd_minimum = 0.046  # V
        self.v_lightsheet_paint_amp_max = 3.6  # V

        self.v_pd_lightsheet = 7.5  # V
        self.v_pd_lightsheet_rampup_start = self.v_pd_lightsheet_pd_minimum  # V
        # self.v_pd_lightsheet_rampup_end = 7.3
        self.v_pd_lightsheet_rampup_end = 9.2  # V
        self.v_pd_lf_lightsheet_rampdown_end = .94  # V  # 4.16
        self.v_pd_hf_lightsheet_rampdown_end = .94  # V  # 4.16
        self.v_pd_hf_lightsheet_rampdown2_end = .25  # V
        self.v_pd_lightsheet_rampdown3_end = .0  # V
        self.n_lightsheet_ramp_steps = 1000  # steps

        # 1064 tweezer
        # self.v_pd_tweezer_1064_pd_minimum = 0.01
        self.amp_tweezer_pid1 = .45  # amplitude (0–1)
        self.amp_tweezer_pid2 = .45  # amplitude (0–1)  # brimrose AO
        self.v_pd_tweezer_1064 = 5.  # V

        self.v_pd_lf_tweezer_1064_ramp_end = 9.2  # V
        self.v_pd_lf_tweezer_1064_rampdown_end = 1.25  # V
        self.v_pd_lf_tweezer_1064_rampdown2_end = .13  # V
        self.v_pd_lf_tweezer_1064_rampdown3_end = 2.  # V

        self.v_pd_hf_tweezer_1064_ramp_end = 9.2  # V
        self.v_pd_hf_tweezer_1064_rampdown_end = 1.13  # V
        self.v_pd_hf_tweezer_1064_rampdown2_end = .18  # V
        self.v_pd_hf_tweezer_1064_rampdown3_end = 2.  # V
        self.n_tweezer_ramp_steps = 1000  # steps

        self.n_tweezers = 2  # count

        self.frequency_tweezer_list1 = [72250000., 72833333.33333333,
                                        73416666.66666667, 74000000.]  # Hz
        self.frequency_tweezer_list2 = [74050000., 74683333.33333333,
                                        75316666.66666667, 75950000.]  # Hz

        self.amp_tweezer_list1 = [.25, .25, .25, .25]  # amplitude (0–1)
        self.amp_tweezer_list2 = [.25, .25, .25, .25]  # amplitude (0–1)

        self.frequency_aod_center = 75.e6  # MHz

        self.frequency_tweezer_list = [75.8e6]  # MHz

        # self.frequency_tweezer_auto_compute = False
        # self.amp_tweezer_auto_compute = True
        self.amp_tweezer_list = [.15]  # amplitude (0–1)

        self.v_lf_tweezer_paint_amp_max = -1.43  # V
        self.v_hf_tweezer_paint_amp_max = -1.1  # V

        self.v_paint_amp_end = -5.4  # V
        self.v_hf_paint_amp_end = -5.25  # V

        # tweezer movement params
        # self.n_steps_tweezer_move = 100
        self.y_tweezer_move = 10.e-6  # m
        self.which_tweezer = 0  # index

        # RF
        self.amp_rf_source = 0.99  # amplitude (fraction of max)
        self.n_rf_sweep_steps = 1000  # steps

        self.t_rf_sweep_state_prep = 100.e-3  # ms
        self.frequency_rf_sweep_state_prep_center = 459.3543e6  # MHz
        self.frequency_rf_sweep_state_prep_fullwidth = 30.e3  # kHz
        
        # RF
        self.t_rf_state_xfer_sweep = 60.e-3  # ms
        self.frequency_rf_state_xfer_sweep_center = 461.7e6  # MHz
        self.frequency_rf_state_xfer_sweep_fullwidth = 2.e6  # MHz

        # feshbach field rampup
        # self.i_feshbach_field_rampup_start = 0.
        self.n_field_ramp_steps = 1000  # steps
        # self.n_feshbach_field_rampup_steps = 100
        # self.n_feshbach_field_ramp_steps = 100
        # self.n_feshbach_field_ramp2_steps = 100

        # rydberg
        self.frequency_ao_ry_405_switch = 80.0e6  # MHz
        self.frequency_ao_ry_980_switch = 80.0e6  # MHz
        self.amp_ao_ry_405_switch = 0.10  # amplitude (0–1)
        self.amp_ao_ry_980_switch = 0.34  # amplitude (0–1)

        # raman
        self.frequency_raman_plus = 150.e6  # MHz
        self.frequency_raman_minus = 80.e6  # MHz
        self.frequency_raman_zeeman_state_xfer_sweep_center = 40.e6  # MHz
        self.frequency_raman_zeeman_state_xfer_sweep_fullwidth = 5.e6  # MHz
        self.fraction_power_raman = 1.  # fraction (0–1)
        self.n_raman_sweep_steps = 100  # steps

        self.frequency_raman_transition = 41.25e6  # MHz

        # low field evap old
        # self.i_evap1_current = 9.5
        # self.i_evap2_current = 31.3
        # self.i_evap3_current = 25.
        # self.i_evap3_current = 16.4

        # low field evap NEW
        self.i_lf_lightsheet_evap1_current = 15.8  # A

        self.i_lf_tweezer_load_current = 15.3  # A
        self.i_lf_tweezer_evap1_current = 13.0  # A
        self.i_lf_tweezer_evap2_current = 13.0  # A

        self.i_spin_mixture = 19.48  # A

        # high field evap
        self.i_hf_lightsheet_evap1_current = 192.1  # A
        self.i_hf_lightsheet_evap2_current = 193.3  # A

        self.i_hf_tweezer_load_current = 192.9  # A
        self.i_hf_tweezer_evap1_current = 192.7  # A
        self.i_hf_tweezer_evap2_current = 193.  # A

        self.i_non_inter = 182.  # A

        # self.i_evap2_current = 198.45
        # self.i_evap3_current = 198.7

        # forced evap
        self.i_forced_evap_ramp_init = 0.  # A
        # self.n_forced_evap_ramp_steps = 1000
        self.i_forced_evap_ramp_end = 40.  # A

        self.compute_derived()

    def compute_gmramp_params(self):
        self.pfrac_c_gmramp_start = self.pfrac_d1_c_gm  # power fraction
        self.pfrac_r_gmramp_start = self.pfrac_d1_r_gm  # power fraction

        self.pfrac_c_gmramp_list = np.linspace(
            self.pfrac_c_gmramp_start,
            self.pfrac_c_gmramp_end,
            self.n_gmramp_steps
        ).transpose()
        self.pfrac_r_gmramp_list = np.linspace(
            self.pfrac_r_gmramp_start,
            self.pfrac_r_gmramp_end,
            self.n_gmramp_steps
        ).transpose()

        cal = DDS_VVA_Calibration()
        self.v_pd_c_gmramp_list = cal.power_fraction_to_vva(
            self.pfrac_c_gmramp_list
        ).transpose()  # V
        self.v_pd_r_gmramp_list = cal.power_fraction_to_vva(
            self.pfrac_r_gmramp_list
        ).transpose()  # V

        self.dt_gmramp = self.t_gmramp / self.n_gmramp_steps  # s per step

    def compute_d1_vvas(self):
        cal = DDS_VVA_Calibration()
        self.v_pd_d1_c_d1cmot = cal.power_fraction_to_vva(
            self.pfrac_d1_c_d1cmot
        )  # V
        self.v_pd_d1_c_gm = cal.power_fraction_to_vva(
            self.pfrac_d1_c_gm
        )  # V
        self.v_pd_d1_r_gm = cal.power_fraction_to_vva(
            self.pfrac_d1_r_gm
        )  # V

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
        self.phase_tweezer_array = np.zeros([len(self.amp_tweezer_list)])  # rad
        for tweezer_idx in range(len(self.amp_tweezer_list)):
            if tweezer_idx == 0:
                self.phase_tweezer_array[0] = 360.  # deg
            else:
                phase_ij = 0
                for j in range(1, tweezer_idx):
                    phase_ij = phase_ij + 2*np.pi*(tweezer_idx - j)*self.amp_tweezer_list[tweezer_idx]
                phase_i = (phase_ij % 2*np.pi) * 360  # deg
                self.phase_tweezer_array[tweezer_idx] = phase_i

    def compute_derived(self):
        '''loop through methods (except built in ones) and compute all derived quantities'''
        methods = [m for m in dir(self)
                   if not m.startswith('__')
                   and callable(getattr(self, m))
                   and not m == 'compute_derived']
        for m in methods:
            getattr(self, m)()
