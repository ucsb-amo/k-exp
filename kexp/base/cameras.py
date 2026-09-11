import pypylon.pylon as py
import numpy as np
import logging
from collections import namedtuple

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


def resolve_camera(camera) -> CameraParams:
    """Accept a CameraParams instance or its key string; return the params.

    Module level, not a method: Base.__init__ has to resolve camera_select
    before any mixin __init__ has run.
    """
    if isinstance(camera,str):
        key = camera
        camera = vars(cameras).get(key)
        if not isinstance(camera,CameraParams):
            raise ValueError(f'The requested camera with key {key} was not found.')
    return camera


RunConfig = namedtuple("RunConfig", "camera capture_frames save_data apd_stage")


def resolve_run_config(camera_select, setup_camera=True, override_apd_stage=None,
                       suppress_live_od=False, save_data=True):
    """Resolve what a run acquires with, and where the APD pickoff stage goes.

    `camera_select` picks the detector; `setup_camera` says whether to acquire
    with it at all:

      a camera,    setup_camera=True  -> liveOD grabs frames; stage out
      cameras.apd, setup_camera=True  -> no liveOD frames (the experiment's own
                                         kernel reads the APD); stage in
      either,      setup_camera=False -> acquire nothing; stage left alone

    suppress_live_od turns off liveOD -- frames and saving -- but not the APD,
    which never goes through liveOD.  override_apd_stage=True/False forces the
    stage for the one case camera_select cannot express: a run that takes
    camera frames *and* reads the APD.

    Returns capture_frames rather than setup_camera: internally
    self.setup_camera means only "liveOD grabs frames", False for the APD.

    A pure function of its arguments -- no hardware, no ARTIQ, no self -- so
    the truth table is testable off the machine.
    """
    camera = resolve_camera(camera_select)
    is_apd = camera.camera_type == "apd"

    if suppress_live_od:
        save_data = False
    capture_frames = setup_camera and not is_apd and not suppress_live_od

    if override_apd_stage is not None:
        apd_stage = override_apd_stage
    elif setup_camera and is_apd:
        apd_stage = True
    elif capture_frames:
        apd_stage = False
    else:
        apd_stage = None

    return RunConfig(camera, capture_frames, save_data, apd_stage)


class Cameras():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.run_info = RunInfo()
        self.ttl = ttl_frame()
        self.slm = SLM()

    ### Camera setup functions ###

    def choose_camera(self,
                      imaging_type=img_types.ABSORPTION,
                      camera=cameras.xy_basler):
        
        camera = resolve_camera(camera)

        # _img_config_bit = img_config.SWITCH
        _img_config_bit = img_config.PID

        # Always configure camera params and TTL regardless of setup_camera.
        # The experiment client needs the correct TTL assigned even when no
        # images are being taken (e.g. save_data=False / setup_camera=False).
        match camera.key:
            case cameras.xy_basler.key:
                ttl = self.ttl.basler
            case cameras.x_basler.key:
                ttl = self.ttl.z_basler
            case cameras.z_basler.key:
                ttl = self.ttl.z_basler
            case cameras.andor.key | cameras.apd.key:
                # The APD sits behind the Andor's pickoff beamsplitter, and
                # keeps clocking the Andor trigger line so its imaging
                # sequence is bit-identical to an Andor run.
                ttl = self.ttl.andor
            case cameras.basler_2dmot.key:
                ttl = self.ttl.basler_2dmot
            case _:
                raise ValueError(
                    f"No camera TTL mapping found for camera key '{camera.key}'."
                )
        self.assign_camera_stuff(camera, camera_ttl=ttl, imaging_type=imaging_type)
        self.run_info.imaging_type = imaging_type
        return _img_config_bit

    @kernel
    def setup_slm(self, imaging_type):
        # optical_path_key, not camera_type: the APD shares the Andor port and
        # needs the same phase mask. (This compared a *type* against a *key*
        # before, which coincided only for the Andor.)
        if self.camera_params.optical_path_key == cameras.andor.key:
            if imaging_type == img_types.ABSORPTION or imaging_type == img_types.ABSORPTION:
                self.slm.write_phase_mask_kernel(0.,0.)
            elif imaging_type == img_types.DISPERSIVE:
                self.slm.write_phase_mask_kernel()

    def assign_camera_stuff(self,
                            camera:CameraParams,
                            camera_ttl:TTL,
                            imaging_type):
        
        self.camera_params = camera
        self.camera_params.select_imaging_type(imaging_type)
        self.ttl.camera = camera_ttl

    def nothing(self):
        pass

    