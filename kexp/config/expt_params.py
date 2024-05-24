import numpy as np
from kexp.config.dds_calibration import DDS_VVA_Calibration

class ExptParams():
    def __init__(self):

        self.t_rtio = 8.e-9

        self.N_shots = 1
        self.N_repeats = 1
        self.N_img = 1
        self.N_shots_with_repeats = 1

        #Magnet
        self.t_keysight_analog_response = 27.2e-3
        self.t_hbridge_switch_delay = 80.e-3
        self.t_contactor_close_delay = 25.e-3
        self.t_contactor_open_delay = 12.e-3

        #Imaging
        self.t_imaging_pulse = 5.e-6
        self.t_light_only_image_delay = 100.e-3
        self.t_dark_image_delay = 25.e-3

        self.frequency_ao_imaging = 350.00e6
        self.frequency_detuned_imaging = 27.e6
        self.frequency_detuned_imaging_F1 = 431.54e6 + 17.e6
        self.imaging_state = 2.
        
        self.t_repump_flash_imaging = 10.e-6
        self.detune_d2_r_imaging = 0.
        self.amp_d2_r_imaging = 0.065

        self.t_cooler_flash_imaging = 15.e-6
        self.detune_d2_c_imaging = 0.
        self.amp_d2_c_imaging = 0.065

        #Cooling timing
        self.t_tof = 20.e-6
        self.t_mot_kill = 1.
        self.t_2D_mot_load_delay = 1.
        self.t_mot_load = 0.5
        self.t_d2cmot = 50.e-3
        self.t_d1cmot = 10.e-3
        self.t_magnet_off_pretrigger = 0.e-3
        self.t_gm = 3.e-3
        self.t_gmramp = 5.e-3
        self.t_optical_pumping = 200.e-6
        self.t_optical_pumping_bias_rampup = 2.e-3
        self.t_lightsheet_rampup = 200.e-3
        self.t_lightsheet_rampdown = 1.1
        self.t_lightsheet_rampdown2 = .7
        self.t_lightsheet_rampdown3 = .02
        self.t_lightsheet_load = 10.e-3
        self.t_lightsheet_hold = 40.e-3
        self.t_tweezer_ramp = 5.e-3
        self.t_tweezer_hold = 30.e-3
        self.t_tweezer_1064_ramp = 10.e-3
        self.t_tweezer_1064_rampdown = 1.
        self.t_mot_reload = 2.
        self.t_bias_off_wait = 20.e-3
        self.t_recover = 40.e-3
        self.t_magtrap = 500.e-3
        self.t_magtrap_ramp = 600.e-3
        self.t_feshbach_field_ramp = 80.e-3

        # DAC controlled AO amplitudes
        self.amp_d1_3d_c = 0.3
        self.amp_d1_3d_r = 0.3

        #push beam
        self.detune_push = -2.4
        self.amp_push = 0.13

        #2D MOT
        self.detune_d2_c_2dmot = -1.2
        self.amp_d2_c_2dmot = 0.188

        self.detune_d2_r_2dmot = -2.4
        self.amp_d2_r_2dmot = 0.188

        self.i_2d_mot = 2.11

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
        self.v_zshim_current = 0.45
        self.v_xshim_current = 4.1
        self.v_yshim_current = 7.

        #D2 CMOT
        self.detune_d2_c_d2cmot = -0.9
        self.amp_d2_c_d2cmot = 0.14

        self.detune_d2_r_d2cmot = -1.5
        self.amp_d2_r_d2cmot = 0.188

        self.v_d2cmot_current = .98

        #D1 CMOT
        self.detune_d1_c_d1cmot = 10.4
        self.pfrac_d1_c_d1cmot = .95

        self.detune_d2_r_d1cmot = -3.2
        self.amp_d2_r_d1cmot = 0.042

        self.detune_d1_c_sweep_d1cmot_start = 9.
        self.detune_d1_c_sweep_d1cmot_end = 7.
        self.detune_d2_r_sweep_d1cmot_start = -3.
        self.detune_d2_r_sweep_d1cmot_end = -5.
        self.n_d1cmot_detuning_sweep_steps = 200

        self.i_cmot = 20.
        
        #GM
        self.detune_gm = 10.4
        # self.amp_gm = 0.09

        self.v_zshim_current_gm = 0.75
        self.v_xshim_current_gm = 0.
        self.v_yshim_current_gm = 1.75

        self.detune_d1_c_gm = self.detune_gm
        self.pfrac_d1_c_gm = .78 # there is an ND on this photodiode -- much higher power/volt than the repump
        self.detune_d1_r_gm = self.detune_gm
        self.pfrac_d1_r_gm = .59

        #Discrete GM ramp
        #v_pd values for start and end of ramp
        self.pfrac_c_gmramp_end = 0.35
        self.pfrac_r_gmramp_end = 0.189
        self.n_gmramp_steps = 200

        # mag trap
        self.i_magtrap_init = 28.
        self.i_magtrap_ramp_end = 66.
        self.n_magtrap_ramp_steps = 1000

        #Optical Pumping
        self.detune_optical_pumping_op = 0.0
        self.amp_optical_pumping_op = 0.22
        self.v_anti_zshim_current_op = 0.
        self.v_zshim_current_op = 0.
        self.v_yshim_current_op = 2.0
        self.v_xshim_current_op = 0.17
        self.detune_optical_pumping_r_op = 0.0
        self.amp_optical_pumping_r_op = 0.25

        #ODT
        # self.amp_lightsheet = 0.6
        # self.frequency_ao_lightsheet = 80.e6
        self.v_pd_lightsheet_pd_minimum = 0.035
        self.amp_painting = 1.0
        self.frequency_painting = 100.e3
        self.v_pd_lightsheet = 8.8
        self.n_lightsheet_rampup_steps = 1000
        self.v_pd_lightsheet_rampup_start = self.v_pd_lightsheet_pd_minimum
        self.v_pd_lightsheet_rampup_end = 8.8

        self.n_lightsheet_rampdown_steps = 10000
        self.v_pd_lightsheet_rampdown_end = 1.

        self.n_lightsheet_rampdown2_steps = 1000
        self.v_pd_lightsheet_rampdown2_end = .18

        self.n_lightsheet_rampdown3_steps = 1000
        self.v_pd_lightsheet_rampdown3_end = .0

        #1064 tweezer
        # self.v_pd_tweezer_1064_pd_minimum = 0.01
        self.v_pd_tweezer_1064 = 2.1
        self.v_pd_tweezer_1064_ramp_start = 5.8
        self.v_pd_tweezer_1064_ramp_end = 2.1
        self.n_tweezer_1064_ramp_steps = 1000
        
        self.v_pd_tweezer_1064_rampdown_end = 5.
        self.n_tweezer_1064_rampdown_steps = 100

        self.n_tweezers = 2

        self.frequency_aod_center = 75.e6

        #frequency of outer most tweezers, to be added / subtracted from the center frequency of 75 MHz
        self.frequency_tweezer_array_width = .9e6

        # RF
        self.t_rf_sweep_state_prep = 100.e-3
        self.frequency_rf_sweep_state_prep_center = 459.3543e6
        self.frequency_rf_sweep_state_prep_fullwidth = 30.e3
        self.n_rf_sweep_state_prep_steps = 1000

        # RF
        self.t_rf_state_xfer_sweep = 60.e-3
        self.amp_rf_source = 0.99
        self.frequency_rf_state_xfer_sweep_center = 461.7e6
        self.frequency_rf_state_xfer_sweep_fullwidth = 2.e6
        self.n_rf_state_xfer_sweep_steps = 1000

        # feshbach field ramp
        self.i_feshbach_field_ramp_start = 130.
        self.i_feshbach_field_ramp_end = 250.0
        self.n_feshbach_field_ramp_steps = 1000

        # rydberg
        self.frequency_ao_ry_405 = 250.0e6
        self.frequency_ao_ry_980 = 80.0e6
        self.amp_ao_ry_405 = 0.2
        self.amp_ao_ry_980 = 0.285

        # evap
        self.i_evap1_current = 13.
        self.i_evap2_current = 13.5
        self.i_evap3_current = 16.4

        self.compute_derived()

    def compute_rf_sweep_params(self):
        self.dt_rf_state_xfer_sweep = self.t_rf_state_xfer_sweep / self.n_rf_state_xfer_sweep_steps
        self._frequency_rf_state_xfer_sweep_start = self.frequency_rf_state_xfer_sweep_center - self.frequency_rf_state_xfer_sweep_fullwidth
        self._frequency_rf_state_xfer_sweep_end = self.frequency_rf_state_xfer_sweep_center + self.frequency_rf_state_xfer_sweep_fullwidth
        self.frequency_rf_state_xfer_sweep_list = np.linspace(
            self._frequency_rf_state_xfer_sweep_start,
            self._frequency_rf_state_xfer_sweep_end,
            self.n_rf_state_xfer_sweep_steps)
        
        self.dt_rf_sweep_state_prep = self.t_rf_sweep_state_prep / self.n_rf_sweep_state_prep_steps
        self._frequency_rf_sweep_state_prep_start = self.frequency_rf_sweep_state_prep_center - self.frequency_rf_sweep_state_prep_fullwidth
        self._frequency_rf_sweep_state_prep_end = self.frequency_rf_sweep_state_prep_center + self.frequency_rf_sweep_state_prep_fullwidth
        self.frequency_rf_sweep_state_prep_list = np.linspace(
            self._frequency_rf_sweep_state_prep_start,
            self._frequency_rf_sweep_state_prep_end,
            self.n_rf_sweep_state_prep_steps)
        
        
    def compute_lightsheet_ramp_params(self):
        self.v_pd_lightsheet_ramp_list = np.linspace(
            self.v_pd_lightsheet_rampup_start,
            self.v_pd_lightsheet_rampup_end,
            self.n_lightsheet_rampup_steps)
        self.dt_lightsheet_ramp = self.t_lightsheet_rampup / self.n_lightsheet_rampup_steps

    def compute_lightsheet_ramp_down_params(self):
        self.v_pd_lightsheet_rampdown_start = self.v_pd_lightsheet_rampup_end
        self.v_pd_lightsheet_ramp_down_list = np.linspace(
            self.v_pd_lightsheet_rampdown_start,
            self.v_pd_lightsheet_rampdown_end,
            self.n_lightsheet_rampdown_steps)
        self.dt_lightsheet_ramp = self.t_lightsheet_rampdown / self.n_lightsheet_rampdown_steps

    def compute_lightsheet_ramp_down2_params(self):
        self.v_pd_lightsheet_rampdown2_start = self.v_pd_lightsheet_rampdown_end
        self.v_pd_lightsheet_ramp_down2_list = np.linspace(
            self.v_pd_lightsheet_rampdown2_start,
            self.v_pd_lightsheet_rampdown2_end,
            self.n_lightsheet_rampdown2_steps)
        self.dt_lightsheet_ramp = self.t_lightsheet_rampdown2 / self.n_lightsheet_rampdown2_steps

    def compute_lightsheet_ramp_down3_params(self):
        self.v_pd_lightsheet_rampdown3_start = self.v_pd_lightsheet_rampdown2_end
        self.v_pd_lightsheet_ramp_down3_list = np.linspace(
            self.v_pd_lightsheet_rampdown3_start,
            self.v_pd_lightsheet_rampdown3_end,
            self.n_lightsheet_rampdown3_steps)
        self.dt_lightsheet_ramp = self.t_lightsheet_rampdown3 / self.n_lightsheet_rampdown3_steps

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
    
    def compute_tweezer_1064_freqs(self):
        min_f = self.frequency_aod_center - self.frequency_tweezer_array_width
        max_f = self.frequency_aod_center + self.frequency_tweezer_array_width
        self.frequency_tweezer_list = np.linspace(min_f, max_f, self.n_tweezers)

    def compute_tweezer_1064_amps(self):
        self.amp_tweezer_list = np.linspace(1 / self.n_tweezers, 1 / self.n_tweezers, self.n_tweezers)

    # def compute_tweezer_1064_phases(self):
    #     self.phase_tweezer_array = np.empty([self.n_tweezers])
    #     for tweezer_idx in self.n_tweezers:
    #         if tweezer_idx == 0:
    #             self.phase_tweezer_array[0] =  360
    #         else:
    #             self.phase_tweezer_array[tweezer_idx] = 360 - 2*np.pi*

    def compute_tweezer_1064_ramp_params(self):
        self.v_pd_tweezer_1064_ramp_list = np.linspace(self.v_pd_tweezer_1064_ramp_start,self.v_pd_tweezer_1064_ramp_end, self.n_tweezer_1064_ramp_steps).transpose()
        self.dt_tweezer_1064_ramp = self.t_tweezer_1064_ramp / self.n_tweezer_1064_ramp_steps

    def compute_tweezer_1064_rampdown_params(self):
        self.v_pd_tweezer_1064_rampdown_start = self.v_pd_tweezer_1064_ramp_end
        self.v_pd_tweezer_1064_rampdown_list = np.linspace(self.v_pd_tweezer_1064_rampdown_start,self.v_pd_tweezer_1064_rampdown_end, self.n_tweezer_1064_rampdown_steps).transpose()
        self.dt_tweezer_1064_rampdown = self.t_tweezer_1064_rampdown / self.n_tweezer_1064_rampdown_steps

    def compute_magtrap_ramp_params(self):
        self.i_magtrap_ramp_start = self.i_magtrap_init
        self.magtrap_ramp_list = np.linspace(self.i_magtrap_ramp_start,self.i_magtrap_ramp_end, self.n_magtrap_ramp_steps).transpose()
        self.dt_magtrap_ramp = self.t_magtrap_ramp / self.n_magtrap_ramp_steps

    def compute_feshbach_field_ramp_params(self):
        self.i_feshbach_field_ramp_start = self.i_evap1_current
        self.i_feshbach_field_ramp_end = self.i_evap2_current
        self.feshbach_field_ramp_list = np.linspace(self.i_feshbach_field_ramp_start,self.i_feshbach_field_ramp_end, self.n_feshbach_field_ramp_steps).transpose()
        self.dt_feshbach_field_ramp = self.t_feshbach_field_ramp / self.n_feshbach_field_ramp_steps

    def compute_derived(self):
        '''loop through methods (except built in ones) and compute all derived quantities'''
        methods = [m for m in dir(self) if not m.startswith('__') and callable(getattr(self,m)) and not m == 'compute_derived']
        for m in methods:
            getattr(self,m)()
        