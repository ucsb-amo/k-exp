import pypylon.pylon as py
import numpy as np

from artiq.experiment import *
from artiq.language.core import delay, parallel, sequential, delay_mu, now_mu

from waxa.data.run_info import RunInfo
from waxa.data.counter import counter

from waxx.control import BaslerUSB, AndorEMCCD, DummyCamera
from waxx.control.beat_lock import BeatLockImagingPID
from waxx.util.artiq.async_print import aprint

from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.expt_params import ExptParams
from kexp.config.camera_id import CameraParams

from kexp.control.painted_lightsheet import lightsheet

import logging
from kexp.calibrations import (high_field_imaging_detuning,
                                low_field_imaging_detuning,
                                low_field_pid_imaging_detuning,
                                I_LF_HF_THRESHOLD)
from kexp.config.camera_id import img_types as img, cameras


dv = -10.e9

class Image():
    def __init__(self):
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.setup_camera = True
        self.run_info = RunInfo()
        self.camera = DummyCamera()
        self.lightsheet = lightsheet()
        self.scan_xvars = []
        self._counter = counter()