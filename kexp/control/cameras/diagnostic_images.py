"""Reference images of the cooling sequence, taken every shot.

``Base.__init__(diagnostic_images=True)`` (the default) makes ``self.diag``
with ``diagnostic_images(expt, enabled)``: a fresh
``kexp.config.camera_id.diagnostic_frame`` bound to this run -- one triggered
camera stream per camera, set up together, and each image given its camera's
trigger TTL and frame index. The sequence takes an image where it belongs::

    self.diag.img_tweezer_load_x.trigger()

``t_offset`` from the cursor, which stays where it was. Nothing is taken with
diagnostics off, during the warm-up shots (``Base.pre_scan`` clears
``active`` around them: no frame is triggered, fetched or stored for a shot
that saves nothing), for a camera that could not be used this run, or for an
image whose ``|t_offset|`` is longer than its ``t_stage``.

Each frame is saved under its key with a ``<key>_meta`` record per shot
(waxa.data.camera_frames) and a ``camera_stream_<key>`` provenance record;
the run file's root attribute ``diagnostic_images`` records every image's
camera, offset, stage, frame index and own settings as the run took them.
The framework is waxx.control.cameras.diagnostic_frame.
"""

from kexp.config.camera_id import camera_trigger_ttl, diagnostic_cameras, diagnostic_frame
from kexp.control.cameras.camera_stream import camera_streams

# camera entry key -> frame keys
DIAGNOSTIC_FRAMES = {e.camera.key: list(e.frames) for e in diagnostic_cameras.entries()}


def diagnostic_images(expt, enabled=True) -> diagnostic_frame:
    """This run's diagnostic frame, bound to ``expt`` (no camera is opened
    with ``enabled`` False)."""
    return diagnostic_frame().bind(
        expt, enabled,
        make_streams=lambda ex, specs: camera_streams(ex, specs),
        trigger_ttl=lambda camera: camera_trigger_ttl(expt.ttl, camera))
