import pypylon.pylon as py
import numpy as np
import logging

from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

from waxa.data.run_info import RunInfo

from waxx.control.artiq.TTL import TTL, DummyTTL
from waxx.control import BaslerUSB, AndorEMCCD, DummyCamera
from waxx.control.slm.slm import SLM
from waxx.control.beat_lock import BeatLockImaging, PolModBeatLock

from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.expt_params import ExptParams
from kexp.config.camera_id import cameras, img_types, CameraParams

class ImagingConfigurations():
    SWITCH = 0
    PID = 1
    POLMOD = 2

img_config = ImagingConfigurations()

class Cameras():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.run_info = RunInfo()
        self.ttl = ttl_frame()
        self.slm = SLM()

    ### Camera setup functions ###

    def choose_camera(self,setup_camera=True,
                      imaging_type=img_types.ABSORPTION,
                      camera=cameras.xy_basler):
        return True

    def assign_camera_stuff(self,
                            camera:CameraParams,
                            camera_ttl:TTL,
                            imaging_type):
        
        self.camera_params = camera
        self.camera_params.select_imaging_type(imaging_type)
        self.ttl.camera = camera_ttl

    def nothing(self):
        pass

    