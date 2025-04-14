from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.control.artiq.TTL import TTL, DummyTTL
from kexp.config.expt_params import ExptParams
from kexp.config.camera_params import cameras, img_types, CameraParams
from kexp.control import BaslerUSB, AndorEMCCD, DummyCamera
from kexp.util.data.run_info import RunInfo
import pypylon.pylon as py
import numpy as np
from kexp.util.artiq.async_print import aprint
import logging

class Cameras():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.run_info = RunInfo()
        self.ttl = ttl_frame()

    ### Camera setup functions ###

    def choose_camera(self,setup_camera=True,
                      imaging_type=img_types.ABSORPTION,
                      camera=cameras.xy_basler):

        if not setup_camera:
            self.camera = DummyCamera()
            self.camera_params = CameraParams()
            # self.start_triggered_grab = self.nothing
            self.ttl.camera = DummyTTL()
        else:
            match camera.key:
                case "xy_basler":
                    ttl = self.ttl.basler
                case "x_basler":
                    ttl = self.ttl.z_basler
                case "z_basler":
                    ttl = self.ttl.z_basler
                case "andor":
                    ttl = self.ttl.andor
                case "basler_2dmot":
                    ttl = self.ttl.basler_2dmot
                case _:
                    raise ValueError("'setup_camera' option is True, but a valid camera was not specified in 'camera_select'.")
            self.assign_camera_stuff(camera,camera_ttl=ttl,imaging_type=imaging_type)
        self.run_info.imaging_type = imaging_type

    def assign_camera_stuff(self,
                            camera:CameraParams,
                            camera_ttl:TTL,
                            imaging_type):
        
        self.camera_params = camera
        self.camera_params.select_imaging_type(imaging_type)
        self.ttl.camera = camera_ttl

    def nothing(self):
        pass

    