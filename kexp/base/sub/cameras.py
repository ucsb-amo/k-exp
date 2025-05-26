from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.control.artiq.TTL import TTL, DummyTTL
from kexp.config.expt_params import ExptParams
from kexp.config.camera_id import cameras, img_types, CameraParams
from kexp.control import BaslerUSB, AndorEMCCD, DummyCamera
from kexp.control.slm.slm import SLM
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
        self.slm = SLM()

    ### Camera setup functions ###

    def choose_camera(self,setup_camera=True,
                      imaging_type=img_types.ABSORPTION,
                      camera=cameras.xy_basler):
        
        if isinstance(camera,str):
            key = camera
            camera = vars(cameras)[key]
            if not isinstance(camera,CameraParams):
                raise ValueError(f'The requested camera with key {key} was not found.')

        if not setup_camera:
            self.camera = DummyCamera()
            self.camera_params = CameraParams()
            # self.start_triggered_grab = self.nothing
            self.ttl.camera = DummyTTL()
        else:
            match camera.key:
                case cameras.xy_basler.key:
                    ttl = self.ttl.basler
                case cameras.x_basler.key:
                    ttl = self.ttl.z_basler
                case cameras.z_basler.key:
                    ttl = self.ttl.z_basler
                case cameras.andor.key:
                    ttl = self.ttl.andor
                case cameras.basler_2dmot.key:
                    ttl = self.ttl.basler_2dmot
                case _:
                    raise ValueError("'setup_camera' option is True, but a valid camera was not specified in 'camera_select'.")
            self.assign_camera_stuff(camera,camera_ttl=ttl,imaging_type=imaging_type)
        self.run_info.imaging_type = imaging_type
        self.setup_slm(imaging_type)

    def setup_slm(self, imaging_type):
        if imaging_type == img_types.ABSORPTION or imaging_type == img_types.ABSORPTION:
            self.slm.write_phase_mask(0.)
        elif imaging_type == img_types.DISPERSIVE:
            self.slm.write_phase_mask()

    def assign_camera_stuff(self,
                            camera:CameraParams,
                            camera_ttl:TTL,
                            imaging_type):
        
        self.camera_params = camera
        self.camera_params.select_imaging_type(imaging_type)
        self.ttl.camera = camera_ttl

    def nothing(self):
        pass

    