class CameraParams():
    def __init__(self):
        self.pixel_size_m = 0.
        self.magnification = 13
        self.exposure_delay = 0.
        self.exposure_time = 0.
        self.connection_delay = 0.
        self.t_camera_trigger = 2.e-6
    
    def select_absorption(self,absorption_bool):
        pass

class BaslerParams(CameraParams):
    def __init__(self,serial_number='40320384'):
        super.__init__()
        self.serial_no = serial_number

        self.pixel_size_m = 3.45 * 1.e-6
        self.magnification = 0.75
        self.exposure_delay = 17 * 1.e-6

        self.exposure_time_fluor = 500.e-6
        self.exposure_time_abs = 19.e-6

    def select_absorption(self,absorption_bool):
        if absorption_bool:
            self.exposure_time = self.exposure_time_abs
        else:
            self.exposure_time = self.exposure_time_fluor

class AndorParams(CameraParams):
    def __init__(self):
        super.__init__()
        self.pixel_size_m = 16.e-6
        self.magnification = 1. # needs to be figured out and updated
        self.exposure_delay = 0. # needs to be updated from docs
        self.connection_delay = 7.6
        self.t_camera_trigger = 10.e-6
        self.t_readout_time = 512 * 3.3e-6
        self.em_gain = 290.
        self.vs_speed = 2
        self.vs_amp = 2

        self.exposure_time_fluor = 10.e-3
        self.exposure_time_abs = 10.e-6

        self.em_gain_fluor = 290.
        self.em_gain_abs = 0.

    def select_absorption(self,absorption_bool):
        if absorption_bool:
            self.exposure_time = self.exposure_time_abs
            self.em_gain = self.em_gain_abs
        else:
            self.exposure_time = self.exposure_time_fluor
            self.em_gain = self.em_gain_fluor

andor_params = AndorParams()
xy_basler_params = BaslerParams(serial_number='40316451')
z_basler_params = BaslerParams(serial_number='40416468')