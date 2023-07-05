from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.expt_params import ExptParams
from kexp.config.camera_params import CameraParams
from kexp.control import BaslerUSB, AndorEMCCD
from kexp.util.data import RunInfo
import pypylon.pylon as py
import numpy as np

class Image():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.run_info = RunInfo()

    ### Imaging sequences ###

    @kernel
    def trigger_camera(self):
        '''
        Written to pretrigger camera such that the camera exposure begins at the
        timeline cursor position where this is called. Returns the timeline
        cursor to this position after pretrigger.
        '''
        delay(-self.params.t_pretrigger * s)
        self.ttl_camera.pulse(self.params.t_camera_trigger * s)
        t_adv = self.params.t_pretrigger - self.params.t_camera_trigger
        delay(t_adv * s)

    @kernel
    def pulse_imaging_light(self,t):
        self.dds.imaging.on()
        delay(t)
        self.dds.imaging.off()

    @kernel
    def pulse_resonant_mot_beams(self,t):
        with parallel:
            self.dds.d2_3d_c.set_dds_gamma(0.)
            self.dds.d2_3d_r.set_dds_gamma(0.)
        with parallel:
            self.dds.d2_3d_c.on()
            self.dds.d2_3d_r.on()
        delay(t)
        with parallel:
            self.dds.d2_3d_c.off()
            self.dds.d2_3d_r.off()

    @kernel
    def abs_image(self):
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)

        delay(self.params.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)

        self.dds.imaging.off()
        delay(self.params.t_dark_image_delay * s)
        self.trigger_camera()

    @kernel
    def fl_image(self):

        self.trigger_camera()
        # self.pulse_imaging_light(self.camera_params.exposure_time * s)
        self.pulse_resonant_mot_beams(self.camera_params.exposure_time * s)

        delay(self.params.t_light_only_image_delay * s)
        self.trigger_camera()
        # self.pulse_imaging_light(self.camera_params.exposure_time * s)
        self.pulse_resonant_mot_beams(self.camera_params.exposure_time * s)

    ### Camera setup functions ###

    @rpc(flags={"async"})
    def start_triggered_grab_basler(self):
        '''
        Start camera waiting for triggers, wait for N images.

        Parameters
        ----------
        N: int
            Number of images to wait for.
        '''
        Nimg = int(self.params.N_img)
        self.camera.StartGrabbingMax(Nimg, py.GrabStrategy_LatestImages)
        count = 0
        while self.camera.IsGrabbing():
            grab = self.camera.RetrieveResult(1000000, py.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                print(f'gotem (img {count+1}/{Nimg})')
                img = np.uint8(grab.GetArray())
                img_t = grab.TimeStamp
                self.images.append(img)
                self.image_timestamps.append(img_t)
                count += 1
            if count >= Nimg:
                break
        self.camera.StopGrabbing()
        self.camera.Close()

    @rpc(flags={"async"})
    def start_triggered_grab_andor(self):
        Nimg = int(self.params.N_img)
        self.images = self.camera.grab(nframes=Nimg,frame_timeout=10.)
        self.image_timestamps = np.zeros( Nimg )

    def get_N_img(self):
        N_img = 1
        msg = ""
        
        for key in self.xvarnames:
            xvar = vars(self.params)[key]
            if not isinstance(xvar,list) and not isinstance(xvar,np.ndarray):
                xvar = [xvar]
            N_img = N_img * len( vars(self.params)[key] )
            msg += f" {len(xvar)} values of {key}."

        msg += f" {N_img} total shots."

        if self.run_info.absorption_image:
            images_per_shot = 3
        else:
            images_per_shot = 2

        N_img = images_per_shot * N_img # 3 images per value of independent variable (xvar)

        msg += f" {N_img} total images expected."
        print(msg)
        self.params.N_img = N_img

