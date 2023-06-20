class CameraParams():
    def __init__(self):
        self.pixel_size_m = 1.
        self.magnification = 1.
        self.exposure_delay = 0.
        self.serial_no = 0.

basler_fluor_camera_params = CameraParams()
basler_fluor_camera_params.pixel_size_m = 3.45 * 1.e-6
basler_fluor_camera_params.magnification = 0.5
basler_fluor_camera_params.exposure_delay = 17 * 1.e-6
basler_fluor_camera_params.serial_no = '40320384'

basler_absorp_camera_params = CameraParams()
basler_absorp_camera_params.pixel_size_m = 3.45 * 1.e-6
basler_absorp_camera_params.magnification = 0.5
basler_absorp_camera_params.exposure_delay = 17 * 1.e-6
basler_absorp_camera_params.serial_no = '40316451'

andor_camera_params = CameraParams()
andor_camera_params.pixel_size_m = 16.e-6
andor_camera_params.magnification = 1. # needs to be figured out and updated
andor_camera_params.exposure_delay = 0. # needs to be updated from docs