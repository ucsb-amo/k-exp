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

from kexp.config.camera_id import img_types as img, cameras


dv = -10.e9

class Image():
    def __init__(self):
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.params = ExptParams()
        self.imaging = BeatLockImagingPID(dds_sw=self.dds.imaging_x_switch,
                                      dds_pid=self.dds.imaging,
                                      dds_beatref=self.dds.beatlock_ref,
                                      expt_params=self.params)
        self.camera_params = CameraParams()
        self.setup_camera = True
        self.run_info = RunInfo()
        self.camera = DummyCamera()
        self.scan_xvars = []
        self._counter = counter()