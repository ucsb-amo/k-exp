class ImagingType():
    def __init__(self):
        self.ABSORPTION = 0
        self.DISPERSIVE = 1
        self.FLUORESCENCE = 2

img_types = ImagingType()

class CameraParams():
    # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
    def __init__(self):
        self.camera_type = ""
        self.key = ""
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.pixel_size_m = 0.
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.magnification = 13
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.exposure_delay = 0.
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.exposure_time = 0.
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.connection_delay = 0.0
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.t_camera_trigger = 2.e-6
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.gain = 0.
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.amp_imaging = 0.
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.resolution = (1,1,)
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.t_light_only_image_delay = 0.
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.t_dark_image_delay = 0.
    
    def select_imaging_type(self,imaging_type):
        pass

class BaslerParams(CameraParams):
    # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
    def __init__(self,serial_number='40320384',
                trigger_source='Line1',
                exposure_time_fluor = 1.e-3, amp_fluorescence=0.5, gain_fluor = 0.,
                exposure_time_abs = 19.e-6, amp_absorption = 0.248, gain_abs = 0.,
                exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248, gain_dispersive = 0.,
                t_light_only_image_delay=25.e-3, t_dark_image_delay=20.e-3,
                resolution = (1200,1920,),
                magnification = 0.75,
                key = ""):
        super().__init__()
        self.key = key
        self.camera_type = "basler"
        self.serial_no = serial_number
        self.trigger_source = trigger_source
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.resolution = resolution
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.pixel_size_m = 3.45 * 1.e-6
        self.magnification = magnification
        self.exposure_delay = 17 * 1.e-6
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.__gain_fluor = gain_fluor
        self.__gain_abs = gain_abs
        self.__gain_dispersive = gain_dispersive
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.__exposure_time_fluor__ = exposure_time_fluor
        self.__exposure_time_abs__ = exposure_time_abs
        self.__exposure_time_dispersive__ = exposure_time_dispersive
        self.__amp_absorption__ = amp_absorption
        self.__amp_fluorescence__ = amp_fluorescence
        self.__amp_dispersive__ = amp_dispersive
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.t_light_only_image_delay = t_light_only_image_delay
        self.t_dark_image_delay = t_dark_image_delay

    def select_imaging_type(self,imaging_type):
        if imaging_type == img_types.ABSORPTION:
            self.amp_imaging = self.__amp_absorption__
            self.exposure_time = self.__exposure_time_abs__
            self.gain = self.__gain_abs
        elif imaging_type == img_types.FLUORESCENCE:
            self.amp_imaging = self.__amp_fluorescence__
            self.exposure_time = self.__exposure_time_fluor__
            self.gain = self.__gain_fluor
        elif imaging_type == img_types.DISPERSIVE:
            self.amp_imaging = self.__amp_dispersive__
            self.exposure_time = self.__exposure_time_dispersive__
            self.gain = self.__gain_dispersive

class AndorParams(CameraParams):
    # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
    def __init__(self,
                 exposure_time_fluor = 25.e-6, amp_fluorescence=0.54, em_gain_fluor = 10.,
                 exposure_time_abs = 10.e-6, amp_absorption=0.1, em_gain_abs = 300.,
                 exposure_time_dispersive=100.e-6, amp_dispersive = 0.106, em_gain_dispersive = 300.,
                 t_light_only_image_delay=75.e-3, t_dark_image_delay=75.e-3,
                 resolution = (512,512,),
                 magnification = 50./3,
                 key = ""):
        super().__init__()
        self.key = key
        self.camera_type = "andor"
        self.pixel_size_m = 16.e-6
        self.magnification = magnification
        self.exposure_delay = 0. # needs to be updated from docs
        self.connection_delay = 8.0
        self.t_camera_trigger = 200.e-9
        self.t_readout_time = 512 * 3.3e-6
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.hs_speed = 0
        self.vs_speed = 1
        self.vs_amp = 3
        self.preamp = 2
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.__em_gain_fluor = em_gain_fluor
        self.__em_gain_abs = em_gain_abs
        self.__em_gain_dispersive = em_gain_dispersive
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.resolution = resolution
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
        self.__exposure_time_fluor__ = exposure_time_fluor
        self.__exposure_time_abs__ = exposure_time_abs
        self.__amp_absorption__ = amp_absorption
        self.__amp_fluorescence__ = amp_fluorescence
        self.__amp_dispersive__ = amp_dispersive
        self.__exposure_time_dispersive__ = exposure_time_dispersive
        # DO NOT ASSIGN DEFAULT PARAMETERS HERE -- INSTEAD ASSIGN THEM IN kexp.config.camera_id!
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