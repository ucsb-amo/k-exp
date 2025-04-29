class ImagingType():
    def __init__(self):
        self.ABSORPTION = 0
        self.DISPERSIVE = 1
        self.FLUORESCENCE = 2

img_types = ImagingType()

class CameraParams():
    def __init__(self):
        self.camera_type = ""
        self.key = ""

        self.pixel_size_m = 0.
        self.magnification = 13
        self.exposure_delay = 0.
        
        self.exposure_time = 0.

        self.connection_delay = 0.0
        self.t_camera_trigger = 2.e-6

        self.amp_imaging = 0.

        self.resolution = (1,1,)

        self.t_light_only_image_delay = 0.
        self.t_dark_image_delay = 0.
    
    def select_imaging_type(self,imaging_type):
        pass

class BaslerParams(CameraParams):
    def __init__(self,serial_number='40320384',
                 trigger_source='Line1',
                 exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                 exposure_time_abs = 19.e-6, amp_absorption = 0.248,
                 exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                 gain = 0.,
                 resolution = (1200,1920,),
                 t_light_only_image_delay=25.e-3,
                 t_dark_image_delay=20.e-3,
                 key = "",
                 magnification = 0.75):
        super().__init__()
        self.key = key
        self.camera_type = "basler"
        self.serial_no = serial_number
        self.trigger_source = trigger_source

        self.resolution = resolution

        self.pixel_size_m = 3.45 * 1.e-6
        self.magnification = magnification
        self.exposure_delay = 17 * 1.e-6

        self.gain = gain

        self.__exposure_time_fluor__ = exposure_time_fluor
        self.__exposure_time_abs__ = exposure_time_abs
        self.__exposure_time_dispersive__ = exposure_time_dispersive
        self.__amp_absorption__ = amp_absorption
        self.__amp_fluorescence__ = amp_fluorescence
        self.__amp_dispersive__ = amp_dispersive
        

        self.t_light_only_image_delay = t_light_only_image_delay
        self.t_dark_image_delay = t_dark_image_delay

    def select_imaging_type(self,imaging_type):
        if imaging_type == img_types.ABSORPTION:
            self.amp_imaging = self.__amp_absorption__
            self.exposure_time = self.__exposure_time_abs__
        elif imaging_type == img_types.FLUORESCENCE:
            self.amp_imaging = self.__amp_fluorescence__
            self.exposure_time = self.__exposure_time_fluor__
        elif imaging_type == img_types.DISPERSIVE:
            self.amp_imaging = self.__amp_dispersive__
            self.exposure_time = self.__exposure_time_dispersive__

class AndorParams(CameraParams):
    def __init__(self,
                 exposure_time_fluor = 10.e-3, amp_fluorescence=0.106,
                 exposure_time_abs = 10.e-6, amp_absorption=0.106,
                 exposure_time_dispersive=100.e-6, amp_dispersive = 0.106,
                 resolution = (512,512,),
                 t_light_only_image_delay=50.e-3,
                 t_dark_image_delay=50.e-3,
                 key = "",
                 magnification = 50./3):
        super().__init__()
        self.key = key
        self.camera_type = "andor"
        self.pixel_size_m = 16.e-6
        self.magnification = magnification
        self.exposure_delay = 0. # needs to be updated from docs
        self.connection_delay = 8.0
        self.t_camera_trigger = 200.e-9
        self.t_readout_time = 512 * 3.3e-6
        self.gain = 1.
        self.hs_speed = 0
        self.vs_speed = 1
        self.vs_amp = 3
        self.preamp = 2

        self.__em_gain_fluor = 10.
        self.__em_gain_abs = 300.
        self.__em_gain_dispersive = 300.

        self.resolution = resolution
        
        self.__exposure_time_fluor__ = exposure_time_fluor
        self.__exposure_time_abs__ = exposure_time_abs
        self.__amp_absorption__ = amp_absorption
        self.__amp_fluorescence__ = amp_fluorescence
        self.__amp_dispersive__ = amp_dispersive
        self.__exposure_time_dispersive__ = exposure_time_dispersive

        self.t_light_only_image_delay = t_light_only_image_delay
        self.t_dark_image_delay = t_dark_image_delay

    def select_imaging_type(self,imaging_type):
        if imaging_type == img_types.ABSORPTION:
            self.amp_imaging = self.__amp_absorption__
            self.exposure_time = self.__exposure_time_abs__
            self.gain = self.__em_gain_abs
        elif imaging_type == img_types.FLUORESCENCE:
            self.amp_imaging = self.__amp_fluorescence__
            self.exposure_time = self.__exposure_time_fluor__
            self.gain = self.__em_gain_fluor
        elif imaging_type == img_types.DISPERSIVE:
            self.amp_imaging = self.__amp_dispersive__
            self.exposure_time = self.__exposure_time_dispersive__
            self.gain = self.__em_gain_dispersive

class camera_frame():
    def __init__(self):
        
        self.andor = AndorParams(amp_absorption=0.08, 
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