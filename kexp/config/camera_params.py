from kexp.config.img_types import img_types as img

class CameraParams():
    def __init__(self):
        self.camera_type = ""
        self.camera_select = ""

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
    
    def select_absorption(self,imaging_type):
        pass

class BaslerParams(CameraParams):
    def __init__(self,serial_number='40320384',
                 trigger_source='Line1',
                 exposure_time_fluor = 500.e-6, amp_fluorescence=0.5,
                 exposure_time_abs = 19.e-6, amp_absorption = 0.248,
                 exposure_time_dispersive=100.e-6, amp_dispersive = 0.248,
                 resolution = (1200,1920,),
                 t_light_only_image_delay=25.e-3,
                 t_dark_image_delay=15.e-3,
                 camera_select = "",
                 magnification = 0.75):
        super().__init__()
        self.camera_select = camera_select
        self.camera_type = "basler"
        self.serial_no = serial_number
        self.trigger_source = trigger_source

        self.resolution = resolution

        self.pixel_size_m = 3.45 * 1.e-6
        self.magnification = magnification
        self.exposure_delay = 17 * 1.e-6

        self.__exposure_time_fluor__ = exposure_time_fluor
        self.__exposure_time_abs__ = exposure_time_abs
        self.__amp_absorption__ = amp_absorption
        self.__amp_fluorescence__ = amp_fluorescence
        self.__amp_dispersive__ = amp_dispersive
        self.__exposure_time_dispersive__ = exposure_time_dispersive

        self.t_light_only_image_delay = t_light_only_image_delay
        self.t_dark_image_delay = t_dark_image_delay

    def select_absorption(self,imaging_type):
        if imaging_type == img.ABSORPTION:
            self.amp_imaging = self.__amp_absorption__
            self.exposure_time = self.__exposure_time_abs__
        elif imaging_type == img.FLUORESCENCE:
            self.amp_imaging = self.__amp_fluorescence__
            self.exposure_time = self.__exposure_time_fluor__
        elif imaging_type == img.DISPERSIVE:
            self.amp_imaging = self.__amp_dispersive__
            self.exposure_time = self.__exposure_time_dispersive__

class AndorParams(CameraParams):
    def __init__(self,
                 exposure_time_fluor = 10.e-3, amp_fluorescence=0.106,
                 exposure_time_abs = 10.e-6, amp_absorption=0.106,
                 exposure_time_dispersive=100.e-6, amp_dispersive = 0.106,
                 resolution = (512,512,),
                 t_light_only_image_delay=25.e-3,
                 t_dark_image_delay=25.e-3,
                 camera_select = "",
                 magnification = 50./3):
        super().__init__()
        self.camera_select = camera_select
        self.camera_type = "andor"
        self.pixel_size_m = 16.e-6
        self.magnification = magnification
        self.exposure_delay = 0. # needs to be updated from docs
        self.connection_delay = 8.0
        self.t_camera_trigger = 200.e-9
        self.t_readout_time = 512 * 3.3e-6
        self.em_gain = 1.
        self.hs_speed = 0
        self.vs_speed = 1
        self.vs_amp = 3
        self.preamp = 2

        self.__em_gain_fluor = 300.
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

    def select_absorption(self,imaging_type):
        if imaging_type == img.ABSORPTION:
            self.amp_imaging = self.__amp_absorption__
            self.exposure_time = self.__exposure_time_abs__
            self.em_gain = self.__em_gain_abs
        elif imaging_type == img.FLUORESCENCE:
            self.amp_imaging = self.__amp_fluorescence__
            self.exposure_time = self.__exposure_time_fluor__
            self.em_gain = self.__em_gain_fluor
        elif imaging_type == img.DISPERSIVE:
            self.amp_imaging = self.__amp_dispersive__
            self.exposure_time = self.__exposure_time_dispersive__
            self.em_gain = self.__em_gain_dispersive

andor_params = AndorParams(camera_select='andor',
                           amp_absorption=0.08,
                           magnification=18.4)
xy_basler_params = BaslerParams(serial_number='40316451',camera_select='xy_basler',
                                amp_absorption=0.18,
                                magnification=0.5)
xy2_basler_params = BaslerParams(serial_number='40411037',camera_select='xy2_basler',
                                 trigger_source='Line2',
                                 amp_absorption=0.33,
                                 magnification=2.1)
x_basler_params = BaslerParams(serial_number='40320384',camera_select='x_basler',
                               trigger_source='Line2')
z_basler_params = BaslerParams(serial_number='40416468',camera_select='z_basler',
                               amp_absorption=0.5,amp_fluorescence=0.5)