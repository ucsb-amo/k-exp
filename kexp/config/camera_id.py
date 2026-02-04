from waxx.control.cameras.camera_param_classes import CameraParams, BaslerParams, AndorParams, img_types
from waxx.config.camera_id import camera_frame as camera_frame_waxx

class camera_frame(camera_frame_waxx):
    def __init__(self):

        self.setup()
        
        # self.andor = AndorParams(amp_absorption=0.284, exposure_time_abs=10.e-6, em_gain_abs=300.,
        #                         amp_fluorescence=0.54, exposure_time_fluor=25.e-6, em_gain_fluor=1.,
        #                         amp_dispersive=0.4, exposure_time_dispersive=5.e-6, em_gain_dispersive=300.,
        #                         magnification=16.4, # based on run 49189, updated 2025-11-20
        #                         t_light_only_image_delay=50.e-3,
                                # t_dark_image_delay=50.e-3)
        
        # note -- for PID being on x (Andor), "amp" here refers to v_pd on the PID photodiode
        self.andor = AndorParams(amp_absorption=2., exposure_time_abs=20.e-6, em_gain_abs=300.,
                                amp_fluorescence=3.90, exposure_time_fluor=25.e-6, em_gain_fluor=1.,
                                amp_dispersive=3.90, exposure_time_dispersive=5.e-6, em_gain_dispersive=300.,
                                magnification=16.4, # based on run 49189, updated 2025-11-20
                                t_light_only_image_delay=50.e-3,
                                t_dark_image_delay=50.e-3)
        
        self.xy_basler = BaslerParams(serial_number='40316451',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.18, gain_abs=24.,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                                    magnification=0.5)
        
        self.x_basler = BaslerParams(serial_number='40320384',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.248,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                                    trigger_source='Line2')
        
        self.z_basler = BaslerParams(serial_number='40416468',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.5,gain_abs=24.,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248)
        
        self.basler_2dmot = BaslerParams(serial_number='40411037',
                                         trigger_source='Line2')
        
        self.cleanup()
        
cameras = camera_frame()

