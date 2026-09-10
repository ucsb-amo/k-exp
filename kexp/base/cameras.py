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


class _Unset():
    """Sentinel for 'the experiment did not pass this argument'.

    None cannot serve: apd_stage=None already means 'leave the stage where it
    is' (kexp/experiments/tools/monitor.py relies on it), and setup_camera=True
    is a legal value equal to the old default.  __bool__ raises so an
    unresolved value fails loudly instead of reading as truthy.
    """
    def __repr__(self):
        return "<unset>"

    def __bool__(self):
        raise TypeError(
            "A Base.__init__ argument was used before it was resolved against "
            "camera_select. This is a bug in resolve_run_config.")


UNSET = _Unset()

RunConfig = namedtuple("RunConfig", "camera setup_camera save_data apd_stage")


def resolve_run_config(camera_select, setup_camera=UNSET, apd_stage=UNSET,
                       suppress_live_od=False, save_data=True):
    """Resolve the detector-dependent Base.__init__ defaults.

    `camera_select` says whether it takes images and where the APD pickoff
    stage belongs, so selecting the APD does not mean setting three coupled
    flags by hand.  Anything the experiment passed explicitly always wins.

    imaging_type is not resolved here: absorption vs dispersive belongs to the
    measurement, not the detector, so Base defaults it like any other argument.

    A pure function of its arguments: no hardware, no ARTIQ, no self.  Base
    cannot be constructed off the machine (prepare_devices needs get_device),
    so this is where the truth table is testable.
    """
    camera = resolve_camera(camera_select)

    if setup_camera is UNSET:
        setup_camera = camera._default_setup_camera
    elif setup_camera and not camera._default_setup_camera:
        raise ValueError(
            f"camera_select={camera.key!r} takes no images -- the pickoff "
            "beamsplitter blocks the camera when it is in. Drop setup_camera, "
            "or select a real camera.")

    if suppress_live_od:
        setup_camera = False
        save_data = False

    # After suppress_live_od, so a suppressed run never moves the stage.
    # apd_stage=None opts out of stage control; apd_stage=True is how an
    # experiment that images *and* reads the APD says so.
    if apd_stage is UNSET:
        apd_stage = camera._default_apd_stage

    return RunConfig(camera, setup_camera, save_data, apd_stage)


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

    