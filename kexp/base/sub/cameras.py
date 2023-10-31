from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.expt_params import ExptParams
import kexp.config.camera_params as camera_params
from kexp.control import BaslerUSB, AndorEMCCD, DummyCamera
from kexp.util.data import RunInfo
import pypylon.pylon as py
import numpy as np
from kexp.util.artiq.async_print import aprint
import logging

class Cameras():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        self.camera_params = camera_params.CameraParams()
        self.run_info = RunInfo()
        self.ttl = ttl_frame()

    ### Camera setup functions ###

    @rpc(flags={"async"})
    def start_triggered_grab_basler(self):
        '''
        Start basler camera waiting for triggers, wait for self.params.N_img
        images.
        '''
        self.camera = BaslerUSB(BaslerSerialNumber=self.camera_params.serial_no,
                                ExposureTime=self.camera_params.exposure_time)
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
        """
        Starts the Andor waiting for self.params.N_img triggers. Default 10
        second timeout.
        """
        self.camera = AndorEMCCD(ExposureTime=self.camera_params.exposure_time,
                                gain = self.camera_params.em_gain,
                                vs_speed=self.camera_params.vs_speed,
                                vs_amp=self.camera_params.vs_amp)
        Nimg = int(self.params.N_img)
        try:
            self.images = self.camera.grab_andor(nframes=Nimg,frame_timeout=10.)
        except Exception:
            logging.exception("An error occurred with the camera grab. Closing the camera connection.")
            self.camera.Close()
        self.image_timestamps = np.zeros( Nimg )

    def choose_camera(self,setup_camera=True,absorption_image=True,basler_imaging=True,andor_imaging=False):
        # allow andor_imaging to override basler_imaging
        if andor_imaging and basler_imaging:
            basler_imaging = False
            absorption_image = False
        if not basler_imaging and not andor_imaging:
            andor_imaging = True
            absorption_image = False

        # choose the correct camera
        if andor_imaging:
            self.ttl.ttl_camera = self.ttl.ttl_andor
            self.camera_params = camera_params.andor_camera_params
            if setup_camera:
                # self.camera = AndorEMCCD(ExposureTime=self.camera_params.exposure_time)
                self.start_triggered_grab = self.start_triggered_grab_andor
        elif basler_imaging:
            self.ttl.ttl_camera = self.ttl.ttl_basler
            if absorption_image:
                self.camera_params = camera_params.basler_absorp_camera_params
            else:
                self.camera_params = camera_params.basler_fluor_camera_params
            if setup_camera:
                # self.camera = BaslerUSB(BaslerSerialNumber=self.camera_params.serial_no,
                #                         ExposureTime=self.camera_params.exposure_time)
                self.start_triggered_grab = self.start_triggered_grab_basler
        
        if not setup_camera:
            self.camera = DummyCamera()
            self.camera_params = camera_params.CameraParams()
            self.start_triggered_grab = self.nothing

        self.run_info.absorption_image = absorption_image
        
        # for backward compatability
        self.StartTriggeredGrab = self.start_triggered_grab

    def nothing(self):
        pass

    