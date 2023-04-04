import kexp.config.camera_params as cam
import numpy as np

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
            