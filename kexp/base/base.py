from artiq.experiment import *
from artiq.experiment import delay_mu, delay

import numpy as np

from kexp.config import ExptParams
from kexp.control import BaslerUSB, AndorEMCCD
from kexp.base.sub import Devices, Cooling, Image, Dealer
from kexp.util.data import DataSaver, RunInfo

import kexp.config.camera_params as camera_params
# also import the andor camera parameters

from kexp.util.artiq.async_print import aprint

class Base(Devices, Cooling, Image, Dealer):
    def __init__(self,setup_camera=True,absorption_image=True,basler_imaging=True,andor_imaging=False):
        super().__init__()
        self.prepare_devices()

        # allow andor_imaging to override basler_imaging
        if andor_imaging and basler_imaging:
            basler_imaging = False
            absorption_image = False
        if not basler_imaging and not andor_imaging:
            andor_imaging = True
            absorption_image = False

        # choose the correct camera
        if setup_camera:
            if andor_imaging:
                self.ttl_camera = self.ttl_andor
                self.StartTriggeredGrab = self.start_triggered_grab_andor
                self.camera_params = camera_params.andor_camera_params
                self.camera = AndorEMCCD(ExposureTime=self.camera_params.exposure_time)
                # raise ValueError("Andor is not set up yet.")
            elif basler_imaging:
                self.ttl_camera = self.ttl_basler
                if absorption_image:
                    self.camera_params = camera_params.basler_absorp_camera_params
                else:
                    self.camera_params = camera_params.basler_fluor_camera_params
                self.camera = BaslerUSB(BaslerSerialNumber=self.camera_params.serial_no,
                                        ExposureTime=self.camera_params.exposure_time)
                self.StartTriggeredGrab = self.start_triggered_grab_basler
        else:
            self.camera_params = camera_params.CameraParams()
            
        self.params = ExptParams(camera_params=self.camera_params)

        self.images = []
        self.image_timestamps = []

        self.run_info = RunInfo(self)
        self._ridstr = " Run ID: "+ str(self.run_info.run_id)
        self.run_info.absorption_image = absorption_image

        self.xvarnames = []
        self.sort_idx = []
        self.sort_N = []

        self.ds = DataSaver()

    
