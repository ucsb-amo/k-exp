from waxx.control.cameras.camera_param_classes import CameraParams, BaslerParams, AndorParams, APDParams, img_types
from waxx.config.camera_id import camera_frame as camera_frame_waxx

class camera_frame(camera_frame_waxx):
    def __init__(self):

        self.setup()

        # Andor DU897_EXF vertical-clock settings. Dark-frame CIC sweep on
        # 2026-09-23 (EM gain 300, 10 us exposure, -63 C, 20 frames/config,
        # fixed threshold = gain-1 bias + 6 sigma):
        #   vs=0.5 us, +3 (old):    2.7e-2 events/pix/frame, readout 18.1 ms
        #   vs=0.3 us, Normal:       3.9e-4 events/pix/frame, readout 17.9 ms
        # 2026-09-24, runs 80707 (0.5 us/+3) vs 80708 (0.3 us/Normal), same
        # beam-only sequence: at 0.3 us / Normal the light frames contain NO
        # image (light - dark peak 38 ADU vs 9400 ADU), dark sigma drops to
        # read noise. The charge is not transferred at that clock, so the low
        # dark-frame count in the sweep was signal loss, not low CIC. Do not
        # use it. Beam check: tools/readout_clock_smear_test.py.
        # Frame gaps: readout 18.1 ms + keep-clean 3.9 ms + margin; 30 ms
        # validated at 0.5 us/+3 in run 80707 (no lost frames).
        self.andor = AndorParams(amp_absorption=.2, exposure_time_abs=10.e-6, em_gain_abs=300.,
                                amp_fluorescence=0.5, exposure_time_fluor=25.e-6, em_gain_fluor=1.,
                                amp_dispersive=0.2, exposure_time_dispersive=5.e-6, em_gain_dispersive=300.,
                                magnification=16.4, # based on run 49189, updated 2025-11-20
                                # t_light_only_image_delay=50.e-3, # 2026-09-23
                                # t_dark_image_delay=50.e-3, # 2026-09-23
                                t_light_only_image_delay=30.e-3, # 2026-09-23
                                t_dark_image_delay=30.e-3, # 2026-09-23
                                hs_speed=0, preamp=2,
                                # vs_speed=0, vs_amp=0, # 2026-09-23; REVERTED: run 80708 shows
                                #   0.3 us / Normal amplitude loses the whole image (charge not
                                #   transferred; the low dark counts were signal loss, not low CIC)
                                vs_speed=1, vs_amp=3) # restored 2026-09-24, run 80707/80708

        self.apd = APDParams(amp_absorption=.2, exposure_time_abs=20.e-6,
                            amp_fluorescence=0.5, exposure_time_fluor=25.e-6,
                            amp_dispersive=0.2, exposure_time_dispersive=5.e-6,
                            t_light_only_image_delay=50.e-3,
                            t_dark_image_delay=50.e-3)

        self.xy_basler = BaslerParams(serial_number='40316451',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.5, gain_abs=6.,
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

