"""Every camera entry names its trigger TTL, and the experiment resolves it
onto its OWN ttl frame (kexp.config.camera_id.camera_trigger_ttl).

Offline: builds ttl frames and camera params only; no devices, no network.
"""
import numpy as np
import pytest

from kexp.config.camera_id import cameras, camera_trigger_ttl, CameraParams
from kexp.config.ttl_id import ttl_frame
from waxx.control.cameras.camera_param_classes import BaslerParams

EXPECTED_CH = {"andor": 7, "apd": 7, "xy_basler": 5, "x_basler": 51,
               "z_basler": 10, "basler_2dmot": 20, "mot_basler": 51}


def _entries():
    return {k: v for k, v in vars(cameras).items() if isinstance(v, CameraParams)}


def test_every_camera_resolves_onto_the_experiments_frame():
    ttl = ttl_frame()                     # the experiment's own frame
    for key, cam in _entries().items():
        t = camera_trigger_ttl(ttl, cam)
        assert t.ch == EXPECTED_CH[key], (key, t.ch)
        assert t is getattr(ttl, cam.trigger_ttl)        # by name
        assert t is not cam._trigger_ttl                 # never the config's own object
        assert cam.trigger_ttl_ch == t.ch


def test_x_basler_and_mot_basler_share_the_mot_trigger_line():
    ttl = ttl_frame()
    assert camera_trigger_ttl(ttl, cameras.x_basler) is camera_trigger_ttl(
        ttl, cameras.mot_basler) is ttl.mot_basler_trigger
    assert cameras.x_basler.trigger_source == cameras.mot_basler.trigger_source == "Line2"


def test_saved_fields_are_plain_and_the_object_is_private():
    """What the INIT_RUN payload takes (vars() without '_' keys) must be
    h5py-storable; the TTL object stays behind an underscore."""
    for key, cam in _entries().items():
        public = {k: v for k, v in vars(cam).items() if not k.startswith("_")}
        assert isinstance(public["trigger_ttl"], str) and public["trigger_ttl"], key
        assert isinstance(public["trigger_ttl_ch"], int), key
        for k, v in public.items():
            assert isinstance(v, (str, int, float, tuple, list, np.generic)), (key, k, type(v))
        assert "_trigger_ttl" not in public


def test_name_only_entry_resolves_by_name_and_channel_is_the_fallback():
    ttl = ttl_frame()
    by_name = BaslerParams(serial_number="1", trigger_ttl="basler_2dmot")
    assert by_name.trigger_ttl_ch == -1 and by_name._trigger_ttl is None
    assert camera_trigger_ttl(ttl, by_name) is ttl.basler_2dmot
    # a renamed line still resolves through the channel
    other = ttl_frame()
    renamed = BaslerParams(serial_number="2", trigger_ttl=other.basler_2dmot)
    renamed.trigger_ttl = "no_such_name"
    assert camera_trigger_ttl(ttl, renamed) is ttl.basler_2dmot


def test_entry_without_trigger_is_refused():
    ttl = ttl_frame()
    none = BaslerParams(serial_number="3")
    none.key = "no_trigger"
    with pytest.raises(ValueError, match="No camera TTL mapping"):
        camera_trigger_ttl(ttl, none)
    with pytest.raises(TypeError):
        BaslerParams(serial_number="4", trigger_ttl=object())
