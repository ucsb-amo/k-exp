from kexp.control.cameras.camera_param_classes import CameraParams, BaslerParams, AndorParams, img_types

class camera_frame():
    def __init__(self):
        
        self.andor = AndorParams(amp_absorption=0.09, exposure_time_abs=15.e-6, em_gain_abs=300.,
                                amp_fluorescence=0.54, exposure_time_fluor=25.e-6, em_gain_fluor=1.,
                                amp_dispersive=0.15, exposure_time_dispersive=100.e-6, em_gain_dispersive=300.,
                                magnification=18.4,
                                t_light_only_image_delay=75.e-3,
                                t_dark_image_delay=75.e-3)
        
        self.xy_basler = BaslerParams(serial_number='40316451',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.32,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                                    magnification=0.5)
        
        self.x_basler = BaslerParams(serial_number='40320384',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.248,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                                    trigger_source='Line2')
        
        self.z_basler = BaslerParams(serial_number='40416468',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.5,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248)
        
        self.basler_2dmot = BaslerParams(serial_number='40411037',
                                         trigger_source='Line2')
        
        self.img_types = img_types
        self.write_keys()
    
    def write_keys(self):
        """Adds the assigned keys to the CameraParams objects so that the
        user-defined names (key) are available with the CameraParams
        objects."""
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],CameraParams):
                self.__dict__[key].key = key
        
cameras = camera_frame()

