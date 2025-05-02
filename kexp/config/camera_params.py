from kexp.control.cameras.camera_params import CameraParams, BaslerParams, AndorParams, img_types

class camera_frame():
    def __init__(self):
        
        self.andor = AndorParams(amp_absorption=0.1, 
                                 magnification=18.4)
        self.xy_basler = BaslerParams(serial_number='40316451',
                                      amp_absorption=0.32,
                                      magnification=0.5)
        self.x_basler = BaslerParams(serial_number='40320384',
                                     trigger_source='Line2')
        self.z_basler = BaslerParams(serial_number='40416468',
                                     amp_absorption=0.5,
                                     amp_fluorescence=0.5)
        self.basler_2dmot = BaslerParams(serial_number='40411037',
                                         trigger_source='Line2',
                                         gain=35.)
        
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