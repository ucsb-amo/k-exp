from kexp.config.camera_params import CameraParams
import numpy as np
from kexp.control.als_remote_control import als_power_to_voltage

from kexp.config.dds_calibration import DDS_VVA_Calibration

default_camera_params = CameraParams()

class ExptParams():
    def __init__(self, camera_params=default_camera_params):

        self._camera_params = camera_params

        self.t_mot_kill = 1.
        self.t_mot_load = 2.
        self.t_mot_reload = 2.

        self.t_rtio_mu = np.int64(8) # get this by running core.ref_multiplier

        self.N_shots = 1
        self.N_repeats = 1
        self.N_img = 1
        
        #Imaging
        self.t_imaging_pulse = 5.e-6
        self.t_light_only_image_delay = 100.e-3
        self.t_dark_image_delay = 25.e-3

        self.frequency_ao_imaging = 350.00e6
        self.frequency_detuned_imaging = 27.e6
        self.amp_imaging_fluor = 0.260
        self.amp_imaging_abs = 0.2
        
        self.t_repump_flash_imaging = 2.e-6
        self.detune_d2_r_imaging = 0.
        self.amp_d2_r_imaging = 0.065

        #Cooling timing
        self.t_2D_mot_load_delay = 1.
        self.t_mot_load = 2.
        self.t_d2cmot = 50.e-3
        self.t_d1cmot = 6.e-3
        self.t_gm = 2.5e-3
        self.t_gmramp = 6.0e-3
        self.t_lightsheet_rampup = 20.e-3
        self.t_lightsheet_load = 10.e-3
        self.t_lightsheet_hold = 30.e-3
        self.t_tweezer_ramp = 3.e-3
        self.t_tweezer_hold = 50.e-3

        #push beam
        self.detune_push = 0.
        self.amp_push = 0.188

        #2D MOT
        self.detune_d2_c_2dmot = .57
        self.amp_d2_c_2dmot = 0.1880
        self.detune_d2_r_2dmot = -2.5
        self.amp_d2_r_2dmot = 0.1880

        #MOT
        self.detune_d2_c_mot = -1.6
        self.amp_d2_c_mot = 0.14
        self.detune_d2_r_mot = -2.4
        self.amp_d2_r_mot = 0.188

        self.detune_d1_c_mot = 0.
        self.v_pd_d1_c_mot = .5
        self.detune_d1_r_mot = 0.
        self.v_pd_d1_r_mot = 5.5

        self.v_mot_current = .75 # 3.4A on 3D MOT coils

        #D2 CMOT
        self.detune_d2_c_d2cmot = -0.9
        self.amp_d2_c_d2cmot = 0.14
        self.detune_d2_r_d2cmot = -1.5
        self.amp_d2_r_d2cmot = 0.188
        self.v_d2cmot_current = .98

        #D1 CMOT
        self.detune_d1_c_d1cmot = 8.5
        self.pfrac_d1_c_d1cmot = 1.0
        self.detune_d2_r_d1cmot = -1.5
        self.amp_d2_r_d1cmot = 0.07
        self.v_d1cmot_current = 0.75
        
        #GM
        self.detune_gm = 8.5
        # self.amp_gm = 0.09

        self.detune_d1_c_gm = self.detune_gm
        self.pfrac_d1_c_gm = 1.0 # there is an ND on this photodiode -- much higher power/volt than the repump
        self.detune_d1_r_gm = self.detune_gm
        self.pfrac_d1_r_gm = 1.0

        #Discrete GM ramp
        #v_pd values for start and end of ramp
        self.pfrac_c_gmramp_start = 1.0
        self.pfrac_c_gmramp_end = 0.75
        self.pfrac_r_gmramp_start = 1.0
        self.pfrac_r_gmramp_end = 0.1
        self.n_gmramp_steps = 100

        #ODT
        self.amp_lightsheet = 0.6
        self.frequency_ao_lightsheet = 80.e6
        self.n_lightsheet_rampup_steps = 500
        self.v_pd_lightsheet_rampup_start = 0.0
        self.v_pd_lightsheet_rampup_end = 4.0

        #1227
        self.frequency_ao_1227 = 80.e6
        self.amp_1227 = .45
        self.v_pd_tweezer_ramp_start = 0.0
        self.v_pd_tweezer_ramp_end = 4.0
        self.n_tweezer_ramp_steps = 50

        self.compute_derived()

    def assign_camera_times(self):
        self.t_camera_exposure = self._camera_params.exposure_time
        self.t_grab_start_wait = self._camera_params.connection_delay
        self.t_pretrigger = self._camera_params.exposure_delay
        self.t_camera_trigger = self._camera_params.t_camera_trigger
        
    def compute_lightsheet_ramp_params(self):
        self.v_pd_lightsheet_ramp_list = np.linspace(
            self.v_pd_lightsheet_rampup_start,
            self.v_pd_lightsheet_rampup_end,
            self.n_lightsheet_rampup_steps)
        self.dt_lightsheet_ramp = self.t_lightsheet_rampup / self.n_lightsheet_rampup_steps

    def compute_gmramp_params(self):
        self.pfrac_c_gmramp_list = np.linspace(self.pfrac_c_gmramp_start, self.pfrac_c_gmramp_end, self.n_gmramp_steps)
        self.pfrac_r_gmramp_list = np.linspace(self.pfrac_r_gmramp_start, self.pfrac_r_gmramp_end, self.n_gmramp_steps)

        cal = DDS_VVA_Calibration()
        self.v_pd_c_gmramp_list = cal.power_fraction_to_vva(self.pfrac_c_gmramp_list)
        self.v_pd_r_gmramp_list = cal.power_fraction_to_vva(self.pfrac_r_gmramp_list)

        self.dt_gmramp = self.t_gmramp / self.n_gmramp_steps

    def compute_d1_vvas(self):
        cal = DDS_VVA_Calibration()
        self.v_pd_d1_c_d1cmot = cal.power_fraction_to_vva(self.pfrac_d1_c_d1cmot)
        self.v_pd_d1_c_gm = cal.power_fraction_to_vva(self.pfrac_d1_c_gm)
        self.v_pd_d1_r_gm = cal.power_fraction_to_vva(self.pfrac_d1_r_gm)

    def compute_tweezer_ramp_params(self):
        self.v_pd_tweezer_ramp_list = np.linspace(self.v_pd_tweezer_ramp_start,self.v_pd_tweezer_ramp_end, self.n_tweezer_ramp_steps)
        self.dt_tweezer_ramp = self.t_tweezer_ramp / self.n_tweezer_ramp_steps

    def compute_derived(self):
        '''loop through methods (except built in ones) and compute all derived quantities'''
        methods = [m for m in dir(self) if not m.startswith('__') and callable(getattr(self,m)) and not m == 'compute_derived']
        for m in methods:
            getattr(self,m)()