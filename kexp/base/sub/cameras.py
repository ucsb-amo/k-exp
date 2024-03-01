from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.control.artiq.TTL import TTL, DummyTTL
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
            grab = self.camera.RetrieveResult(10000, py.TimeoutHandling_ThrowException)
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

    def choose_camera(self,setup_camera=True,absorption_image=True,camera_select="xy_basler"):

        if not setup_camera:
            self.camera = DummyCamera()
            self.camera_params = camera_params.CameraParams()
            self.start_triggered_grab = self.nothing
            self.ttl.camera = DummyTTL()
        else:
            match camera_select:
                case "xy_basler":
                    ttl = self.ttl.xy_basler
                    self.assign_camera_stuff(camera_params.xy_basler_params,
                                            camera_ttl=ttl,
                                            grab_loop_method=self.start_triggered_grab_basler,
                                            absorption_bool=absorption_image)
                case "z_basler":
                    ttl = self.ttl.z_basler
                    self.assign_camera_stuff(camera_params.z_basler_params,
                                             camera_ttl=ttl,
                                             grab_loop_method=self.start_triggered_grab_basler,
                                             absorption_bool=absorption_image)
                case "andor":
                    ttl = self.ttl.andor
                    self.assign_camera_stuff(camera_params.andor_params,
                                             camera_ttl=ttl,
                                             grab_loop_method=self.start_triggered_grab_andor,
                                             absorption_bool=absorption_image)
                case _:
                    raise ValueError("'setup_camera' option is True, but a valid camera was not specified in 'camera_select'.")
                
        self.run_info.absorption_image = absorption_image
        self.StartTriggeredGrab = self.start_triggered_grab # for backward compatability

    def assign_camera_stuff(self,
                            camera_params:camera_params.CameraParams,
                            camera_ttl:TTL,
                            grab_loop_method,
                            absorption_bool):
        
        self.camera_params = camera_params
        self.camera_params.select_absorption(absorption_bool)
        self.ttl.camera = camera_ttl
        self.start_triggered_grab = grab_loop_method

    def nothing(self):
        pass

        

    