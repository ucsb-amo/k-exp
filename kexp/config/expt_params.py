import kexp.config.camera_params as cam
import numpy as np

class ExptParams():
    def __init__(self):
        
        self.t_camera_trigger = 2.e-6
        self.t_imaging_pulse = 5.e-6
        self.t_light_only_image_delay = 100.e-3
        self.t_dark_image_delay = 25.e-3
        self.t_camera_exposure = 0. # camera init will default to min exposure
        self.t_grab_start_wait = 0.5
        self.t_pretrigger = cam.exposure_delay

        self.t_rtio_mu = np.int64(8) # get this by running core.ref_multiplier

        self.N_shots = 2
        self.N_repeats = 1
        self.N_img = 1

        #Cooling timing
        self.t_2D_mot_load_delay = 1
        self.t_mot_load = 3
        self.t_d2cmot = 5.e-3
        self.t_d1cmot = 7.e-3
        self.t_gm = 7e-3
        self.t_gm_ramp = 5.e-3

        #MOT
        self.detune_d2_c_mot = -3.3
        self.amp_d2_c_mot = 0.188
        self.detune_d2_r_mot = -4.7
        self.amp_d2_r_mot = 0.188

        self.detune_d1_c_mot = 3.25
        self.amp_d1_c_mot = 0.0963
        self.detune_d1_r_mot = 3.25
        self.amp_d1_r_mot = 0.0955

        #D2 CMOT
        self.detune_d2_c_d2cmot = -.9
        self.amp_d2_c_d2cmot = 0.188
        self.detune_d2_r_d2cmot = -3.7
        self.amp_d2_r_d2cmot = 0.188

        #D1 CMOT
        self.detune_d1_c_d1cmot = 7.6
        self.amp_d1_c_d1cmot = 0.1800
        self.detune_d2_r_d1cmot = -4.2
        self.amp_d2_r_d1cmot = 0.079
        
        #GM
        self.detune_d1_c_gm = 8.0
        self.amp_d1_c_gm = 0.1880
        self.detune_d1_r_gm = 7.8
        self.amp_d1_r_gm = 0.0790

        #GM ramp
        self.power_ramp_factor_gmramp = 20
        self.power_ramp_steps_gmramp = 100

        #Fields
        self.V_mot_current = 0.7 # 3.4A on 3D MOT coils
        self.V_d2cmot_current = 1.5
        self.V_d1cmot_current = .5
            