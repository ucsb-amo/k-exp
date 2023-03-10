class ExptParams():
    def __init__(self):
        self.t_mot_load_s = 1
        self.t_camera_trigger_s = 2.e-6
        self.t_imaging_pulse_s = 5.e-6
        self.t_light_only_image_delay_s = 100.e-3
        self.t_dark_image_delay_s = 10.e-3

    def params_to_dataset(self,expt):
        try:
            param_keys = list(vars(self))
            for key in param_keys:
                value = vars(self)[key]
                expt.set_dataset(key, value)
        except Exception as e: 
            print(e)
            