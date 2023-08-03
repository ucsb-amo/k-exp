from kexp.config.camera_params import CameraParams
import numpy as np

camera_params = CameraParams()

class ExptParams():
    def __init__(self, camera_params=camera_params):

        self.t_mot_kill = 1.
        self.t_mot_load = 2.
        self.t_mot_reload = 2.
        self.t_camera_trigger = camera_params.t_camera_trigger
        self.t_imaging_pulse = 5.e-6
        self.t_light_only_image_delay = 100.e-3
        self.t_dark_image_delay = 25.e-3
        self.t_camera_exposure = 0. # camera init will default to min exposure
        self.t_grab_start_wait = camera_params.connection_delay
        self.t_pretrigger = camera_params.exposure_delay

        self.t_rtio_mu = np.int64(8) # get this by running core.ref_multiplier

        self.N_shots = 1
        self.N_repeats = 1
        self.N_img = 1
        
        #Imaging
        self.frequency_detuned_imaging = 27.e6

        #Cooling timing
        self.t_2D_mot_load_delay = 1.
        self.t_mot_load = 2.
        self.t_d2cmot = 5.e-3
        self.t_d1cmot = 7.e-3
        self.t_gm = 2.5e-3
        self.t_gm_ramp = 2.e-3

        #push beam
        self.detune_push = 2.9
        self.amp_push = 0.188

        #2D MOT
        self.detune_d2_c_2dmot = .57
        self.amp_d2_c_2dmot = 0.1880
        self.detune_d2_r_2dmot = -3.
        self.amp_d2_r_2dmot = 0.1880

        #MOT
        self.detune_d2_c_mot = -0.2
        self.amp_d2_c_mot = 0.2
        self.detune_d2_r_mot = -4.
        self.amp_d2_r_mot = 0.073

        self.detune_d1_c_mot = 3.25
        self.v_pd_d1_c_mot = 1.8
        self.detune_d1_r_mot = 3.25
        self.v_pd_d1_r_mot = 2.4

        self.v_mot_current = .8 # 3.4A on 3D MOT coils

        #D2 CMOT
        self.detune_d2_c_d2cmot = -0.5
        self.amp_d2_c_d2cmot = 0.188
        self.detune_d2_r_d2cmot = -2.5
        self.amp_d2_r_d2cmot = 0.188
        self.v_d2cmot_current = 2.5

        #D1 CMOT
        self.detune_d1_c_d1cmot = 6.4
        self.v_pd_d1_c_d1cmot = 3.0
        self.detune_d2_r_d1cmot = -2.3
        self.amp_d2_r_d1cmot = 0.03

        self.v_d1cmot_current = .0
        
        #GM
        self.detune_gm = 7.2
        # self.amp_gm = 0.09

        self.detune_d1_c_gm = self.detune_gm
        self.v_pd_d1_c_gm = 3.2 # there is an ND on this photodiode -- much higher power/volt than the repump
        self.detune_d1_r_gm = self.detune_gm
        self.v_pd_d1_r_gm = 1.1

        #GM ramp
        self.power_ramp_factor_gmramp = 10

        #1227
        self.frequency_ao_1227 = 80.e6
        self.amp_1227 = .45
        
            