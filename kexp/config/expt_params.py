import kexp.config.camera_params as cam
import numpy as np
from kexp.config.dds_id import dds_frame

dds = dds_frame()

class ExptParams():
    def __init__(self):
        self.t_mot_load = 1
        self.t_2D_mot_load_delay = 1
        self.t_camera_trigger = 2.e-6
        self.t_imaging_pulse = 5.e-6
        self.t_light_only_image_delay = 100.e-3
        self.t_dark_image_delay = 25.e-3
        self.t_camera_exposure = 0. # camera init will default to min exposure
        self.t_grab_start_wait = 1.5

        self.V_mot_current = 0.7 # 3.4A on 3D MOT coils

        self.t_pretrigger = cam.exposure_delay

        self.t_rtio_mu = np.int64(8) # get this by running core.ref_multiplier

        self.N_shots = 2
        self.N_repeats = 1
        self.N_img = 1

        #MOT detunings

        self.detune_d2_c_mot = -3.3
        self.att_d2_c_mot = dds.d2_3d_c.att_dB
        self.detune_d2_r_mot = -4.7
        self.att_d2_r_mot = dds.d2_3d_r.att_dB

        #CMOT detunings
        self.detune_d2_c_d2cmot = -.9
        self.att_d2_c_d2cmot = dds.d2_3d_c.att_dB
        self.detune_d2_r_d2cmot = -3.7
        self.att_d2_r_d2cmot = 12.5

        self.detune_d1_c_d1cmot = 1.29
        self.att_d1_c_d1cmot = 11.5
        self.detune_d2_r_d1cmot = -3.7
        self.att_d2_r_d1cmot = self.att_d2_r_d2cmot

        #GM Detunings
        self.detune_d1_c_gm = 1.29
        self.att_d1_c_gm = 11.5
        self.detune_d1_r_gm = 3.21
        self.att_d1_r_gm = 11.0

        #MOT current settings
        self.V_d2cmot_current = 1.5
        self.V_d1cmot_current = .5
            