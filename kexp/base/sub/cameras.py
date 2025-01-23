from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.control.artiq.TTL import TTL, DummyTTL
from kexp.config.expt_params import ExptParams
import kexp.config.camera_params as camera_params
from kexp.control import BaslerUSB, AndorEMCCD, DummyCamera
from kexp.util.data.run_info import RunInfo
import pypylon.pylon as py
import numpy as np
from kexp.util.artiq.async_print import aprint
import logging
from kexp.config.img_types import img_types as img

class Cameras():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        self.camera_params = camera_params.CameraParams()
        self.run_info = RunInfo()
        self.ttl = ttl_frame()

    ### Camera setup functions ###

    def choose_camera(self,setup_camera=True,imaging_type=img.ABSORPTION,camera_select="xy_basler"):

        if not setup_camera:
            self.camera = DummyCamera()
            self.camera_params = camera_params.CameraParams()
            self.start_triggered_grab = self.nothing
            self.ttl.camera = DummyTTL()
        else:
            match camera_select:
                case "xy_basler":
                    ttl = self.ttl.basler
                    self.assign_camera_stuff(camera_select,
                                            camera_ttl=ttl,
                                            imaging_type=imaging_type)
                case "xy2_basler":
                    ttl = self.ttl.z_basler
                    self.assign_camera_stuff(camera_select,
                                            camera_ttl=ttl,
                                            imaging_type=imaging_type)
                case "x_basler":
                    ttl = self.ttl.z_basler
                    self.assign_camera_stuff(camera_select,
                                            camera_ttl=ttl,
                                            imaging_type=imaging_type)
                case "z_basler":
                    ttl = self.ttl.z_basler
                    self.assign_camera_stuff(camera_select,
                                             camera_ttl=ttl,
                                             imaging_type=imaging_type)
                case "andor":
                    ttl = self.ttl.andor
                    self.assign_camera_stuff(camera_select,
                                             camera_ttl=ttl,
                                             imaging_type=imaging_type)
                case _:
                    raise ValueError("'setup_camera' option is True, but a valid camera was not specified in 'camera_select'.")
            self.assign_camera_stuff(camera_select,camera_ttl=ttl,imaging_type=imaging_type)
        self.run_info.imaging_type = imaging_type

    def assign_camera_stuff(self,
                            camera_select:str,
                            camera_ttl:TTL,
                            imaging_type):
        
        self.camera_params = self.get_camera_params(camera_select)
        self.camera_params.camera_select = camera_select
        self.camera_params.select_absorption(imaging_type)
        self.ttl.camera = camera_ttl

    def get_camera_params(self,camera_select) -> camera_params.CameraParams:
        return vars(camera_params)[camera_select + "_params"]

    def nothing(self):
        pass

        

    