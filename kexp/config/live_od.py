"""kexp's configuration for liveOD.

liveOD itself lives in waxx (waxx.util.live_od) and is lab-independent; this is
everything the K machine tells it. The launcher
(kexp/util/live_od/gui/main_window.py, i.e. _bat/live_od.bat) calls
``make_live_od_config()`` and hands the result to waxx.

Imports are inside the function on purpose: importing this module must stay free
of side effects. kexp.config.ip touches the data drive and executes the device
db; kexp.config.camera_id builds the camera table.
"""

# Camera bar: the buttons of the liveOD window, left to right. (Also the order of
# the camera buttons in the remote viewer, which follows the CAMERA_STATE
# broadcast. Before the move to waxx the local bar was laid out in this order and
# the broadcast listed x before z; there is now one order.)
CAMERA_BAR_KEYS = ("xy_basler", "basler_2dmot", "z_basler", "x_basler", "andor")
# Opened as soon as the window starts. None: every camera starts closed, as before.
CAMERAS_OPEN_ON_START = ()


def _default_roi_id_for(camera_key):
    """Saved-ROI ids (rows of roi.xlsx) liveOD starts from."""
    if "andor" in camera_key:
        return "andor_all"
    if "basler" in camera_key:
        return "basler_all"
    return None


def make_live_od_config():
    """Build the waxx LiveODConfig for the K machine."""
    from waxa.data import DataSaver
    from waxx.util.live_od.config import LiveODConfig

    # liveOD divides integrated OD by a cross section chosen per shot from the
    # field at imaging -- the same rule the analysis applies to the saved run
    # (waxa.calibrations.cross_section, on the recorded outer-coil current).
    from waxx.util.live_od.shot_cross_section import cross_section_for_shot

    from kexp.config.ip import server_talk, PATHS
    from kexp.config.camera_id import cameras
    from kexp.config.expt_params import ExptParams

    def resolve_camera_params(camera_key):
        for value in vars(cameras).values():
            key = getattr(value, "key", None)
            if isinstance(key, bytes):
                key = key.decode()
            if key is not None and key == camera_key:
                return value
        return None

    return LiveODConfig(
        data_saver=DataSaver(*PATHS, server_talk=server_talk),
        run_id_source=server_talk,
        camera_params_list=[getattr(cameras, key) for key in CAMERA_BAR_KEYS],
        cameras_open_on_start=list(CAMERAS_OPEN_ON_START),
        resolve_camera_params=resolve_camera_params,
        default_roi_id_for=_default_roi_id_for,
        params_factory=ExptParams,
        cross_section_for_shot=cross_section_for_shot,
        # Kept exactly as it was: the pinned taskbar button's identity.
        app_user_model_id="weldlab.kexp.gui.live_od",
        window_title="LiveOD Server",
    )
