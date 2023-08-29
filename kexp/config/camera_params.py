class CameraParams():
    def __init__(self):
        self.pixel_size_m = 1.
        self.magnification = 1.
        self.exposure_delay = 0.
        self.serial_no = 0.
        self.exposure_time = 0.
        self.connection_delay = 1.5
        self.t_camera_trigger = 2.e-6
        self.t_readout_time = 0.
        self.em_gain = 250.
        self.vs_speed = 0
        self.vs_amp = 0

basler_fluor_camera_params = CameraParams()
basler_fluor_camera_params.pixel_size_m = 3.45 * 1.e-6
basler_fluor_camera_params.magnification = 0.75
basler_fluor_camera_params.exposure_delay = 17 * 1.e-6
basler_fluor_camera_params.serial_no = '40320384'
basler_fluor_camera_params.exposure_time = 500.e-6

basler_absorp_camera_params = CameraParams()
basler_absorp_camera_params.pixel_size_m = 3.45 * 1.e-6
basler_absorp_camera_params.magnification = 0.5
basler_absorp_camera_params.exposure_delay = 17 * 1.e-6
basler_absorp_camera_params.serial_no = '40316451'
basler_absorp_camera_params.exposure_time = 19.e-6

andor_camera_params = CameraParams()
andor_camera_params.pixel_size_m = 16.e-6
andor_camera_params.magnification = 1. # needs to be figured out and updated
andor_camera_params.exposure_delay = 0. # needs to be updated from docs
andor_camera_params.exposure_time = 10.e-3
andor_camera_params.connection_delay = 7.6
andor_camera_params.t_camera_trigger = 10.e-6
andor_camera_params.t_readout_time = 512 * 3.3e-6
andor_camera_params.em_gain = 290.
andor_camera_params.vs_speed = 2
andor_camera_params.vs_amp = 2