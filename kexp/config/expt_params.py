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
        self.t_keysight_analog_response = 10.e-3
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
        self.t_d1cmot = 7.5e-3
        self.t_magnet_off_pretrigger = 0.e-3
        self.t_gm = 3.e-3
        self.t_gmramp = 5.e-3
        self.t_optical_pumping = 200.e-6
        self.t_optical_pumping_bias_rampup = 2.e-3
        self.t_lightsheet_rampup = 10.e-3
        self.t_lightsheet_rampdown = 1.4
        self.t_lightsheet_rampdown2 = 1.7
        self.t_lightsheet_load = 10.e-3
        self.t_lightsheet_hold = 40.e-3
        self.t_tweezer_ramp = 5.e-3
        self.t_tweezer_hold = 30.e-3
        self.t_tweezer_1064_ramp = 10.e-3
        self.t_tweezer_1064_rampdown = 1.
        self.t_mot_reload = 2.
        self.t_bias_off_wait = 20.e-3
        self.t_recover = 40.e-3
        self.t_magtrap = 40.e-3
        self.t_magtrap_ramp = 40.e-3
        self.t_feshbach_field_ramp = 80.e-3

        # DAC controlled AO amplitudes
        self.amp_d1_3d_c = 0.3
        self.amp_d1_3d_r = 0.3

        #push beam
        self.detune_push = 0.
        self.amp_push = 0.12

        #2D MOT
        self.detune_d2_c_2dmot = -.6
        self.amp_d2_c_2dmot = 0.188

        self.detune_d2_r_2dmot = -2.4
        self.amp_d2_r_2dmot = 0.188

        #MOT
        self.detune_d2_c_mot = -2.2
        self.amp_d2_c_mot = 0.188

        self.detune_d2_r_mot = -3.5
        self.amp_d2_r_mot = 0.188

        self.detune_d1_c_mot = 0.
        self.v_pd_d1_c_mot = 5.0

        self.detune_d1_r_mot = 0.
        self.v_pd_d1_r_mot = 5.0

        self.i_mot = 33.0
        self.v_zshim_current = 0.2
        self.v_xshim_current = 0.993
        self.v_yshim_current = 0.955

        #D2 CMOT
        self.detune_d2_c_d2cmot = -0.9
        self.amp_d2_c_d2cmot = 0.14

        self.detune_d2_r_d2cmot = -1.5
        self.amp_d2_r_d2cmot = 0.188

        self.v_d2cmot_current = .98

        #D1 CMOT
        self.detune_d1_c_d1cmot = 9.
        self.pfrac_d1_c_d1cmot = .8

        self.detune_d2_r_d1cmot = -3.
        self.amp_d2_r_d1cmot = 0.047

        self.detune_d1_c_sweep_d1cmot_start = 9.
        self.detune_d1_c_sweep_d1cmot_end = 7.
        self.detune_d2_r_sweep_d1cmot_start = -3.
        self.detune_d2_r_sweep_d1cmot_end = -5.
        self.n_d1cmot_detuning_sweep_steps = 200

        self.i_cmot = 33.
        
        #GM
        self.detune_gm = 9.
        # self.amp_gm = 0.09

        self.v_zshim_current_gm = 0.9
        self.v_xshim_current_gm = 0.17
        self.v_yshim_current_gm = 2.0

        self.detune_d1_c_gm = self.detune_gm
        self.pfrac_d1_c_gm = .78 # there is an ND on this photodiode -- much higher power/volt than the repump
        self.detune_d1_r_gm = self.detune_gm
        self.pfrac_d1_r_gm = .5

        #Discrete GM ramp
        #v_pd values for start and end of ramp
        self.pfrac_c_gmramp_start = .78
        self.pfrac_c_gmramp_end = 0.45
        self.pfrac_r_gmramp_start = .3
        self.pfrac_r_gmramp_end = 0.097
        self.n_gmramp_steps = 200

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
        self.amp_painting = 1.0
        self.frequency_painting = 100.e3
        self.v_pd_lightsheet = 8.88
        self.n_lightsheet_rampup_steps = 1000
        self.v_pd_lightsheet_rampup_start = 0.035
        self.v_pd_lightsheet_rampup_end = 8.88

        self.n_lightsheet_rampdown_steps = 10000

        self.v_pd_lightsheet_rampdown_end = .864

        self.n_lightsheet_rampdown2_steps = 1000
        
        self.v_pd_lightsheet_rampdown2_end = .152

        #1064 tweezer
        self.v_pd_tweezer_1064 = 4.5
        self.v_pd_tweezer_1064_ramp_start = 0.024
        self.v_pd_tweezer_1064_ramp_end = 4.5
        self.n_tweezer_1064_ramp_steps = 100
        
        self.v_pd_tweezer_1064_rampdown_end = 0.43821/2
        self.n_tweezer_1064_rampdown_steps = 100

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

        # mag trap
        self.i_magtrap_init = 40.
        self.i_magtrap_ramp_start = 74.
        self.i_magtrap_ramp_end = 0.0
        self.n_magtrap_ramp_steps = 1000

        # feshbach field ramp
        self.i_feshbach_field_ramp_start = 130.
        self.i_feshbach_field_ramp_end = 250.0
        self.n_feshbach_field_ramp_steps = 1000

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

    def compute_gmramp_params(self):
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
    
    def compute_tweezer_1064_ramp_params(self):
        self.v_pd_tweezer_1064_ramp_list = np.linspace(self.v_pd_tweezer_1064_ramp_start,self.v_pd_tweezer_1064_ramp_end, self.n_tweezer_1064_ramp_steps).transpose()
        self.dt_tweezer_1064_ramp = self.t_tweezer_1064_ramp / self.n_tweezer_1064_ramp_steps

    def compute_tweezer_1064_rampdown_params(self):
        self.v_pd_tweezer_1064_rampdown_start = self.v_pd_tweezer_1064_ramp_end
        self.v_pd_tweezer_1064_rampdown_list = np.linspace(self.v_pd_tweezer_1064_rampdown_start,self.v_pd_tweezer_1064_rampdown_end, self.n_tweezer_1064_rampdown_steps).transpose()
        self.dt_tweezer_1064_rampdown = self.t_tweezer_1064_rampdown / self.n_tweezer_1064_rampdown_steps

    def compute_magtrap_ramp_params(self):
        self.magtrap_ramp_list = np.linspace(self.i_magtrap_ramp_start,self.i_magtrap_ramp_end, self.n_magtrap_ramp_steps).transpose()
        self.dt_magtrap_ramp = self.t_magtrap_ramp / self.n_magtrap_ramp_steps

    def compute_feshbach_field_ramp_params(self):
        self.feshbach_field_ramp_list = np.linspace(self.i_feshbach_field_ramp_start,self.i_feshbach_field_ramp_end, self.n_feshbach_field_ramp_steps).transpose()
        self.dt_feshbach_field_ramp = self.t_feshbach_field_ramp / self.n_feshbach_field_ramp_steps

    def compute_derived(self):
        '''loop through methods (except built in ones) and compute all derived quantities'''
        methods = [m for m in dir(self) if not m.startswith('__') and callable(getattr(self,m)) and not m == 'compute_derived']
        for m in methods:
            getattr(self,m)()
        