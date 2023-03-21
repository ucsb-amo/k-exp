import kexp.config.camera_params as cam

class ExptParams():
    def __init__(self):
        self.t_mot_load = 1
        self.t_2D_mot_load_delay = 1
        self.t_camera_trigger = 2.e-6
        self.t_imaging_pulse = 5.e-6
        self.t_light_only_image_delay = 100.e-3
        self.t_dark_image_delay = 25.e-3
        self.t_camera_exposure = 0. # camera init will default to min exposure
        self.t_grab_start_wait = 0.25

        self.V_mot_current = 0.7 # 3.4A on 3D MOT coils

        self.t_pretrigger = cam.exposure_delay

    def params_to_dataset(self,expt):
        try:
            param_keys = list(vars(self))
            for key in param_keys:
                value = vars(self)[key]
                expt.set_dataset(key, value)
        except Exception as e: 
            print(e)
            