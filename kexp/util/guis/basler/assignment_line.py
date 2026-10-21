"""The camera viewer's "Copy assignment line" (right-click on Save), in this
lab's words: image lines of kexp.config.camera_id's ``diagnostic_frame``
with the viewer's current exposure, gain and ROI in them.

* the viewer shows one frame key alone (Options -> Frames): that image's line;
* otherwise: one line per image the camera takes, each given the viewer's
  values (an image that ran at its own exposure / gain gets them too: check
  before pasting);
* a camera with no image yet: a new image line to rename and time.

    self.img_mot_beams_z = self.image(cameras.z_basler, t_offset=0.005, exposure_time=1.9e-05, gain=0.0, roi=[660, 300, 1260, 900], label='MOT beams')

``install()`` registers it with the viewer; the dashboards and
``camera_viewer_app`` call it at start-up.
"""


def diagnostic_assignment_line(info: dict) -> str:
    from kexp.config.camera_id import CameraParams, DiagnosticImage, cameras, diagnostic_cameras

    serial = str(info.get("serial") or "")
    cam_key = next((k for k, v in vars(cameras).items()
                    if isinstance(v, CameraParams)
                    and str(getattr(v, "serial_no", "")) == serial), None)
    values = {k: info.get(k) for k in ("exposure_time", "gain", "roi")}
    entry = next((e for e in diagnostic_cameras.entries() if e.camera.key == cam_key), None)
    if entry is not None:
        tag = info.get("frame_tag")
        if tag in entry.frames:
            return getattr(diagnostic_cameras, tag).assignment(**values)
        return entry.assignment(**values)

    name = cam_key or str(info.get("name") or "camera").replace(" ", "_")
    if not cam_key:
        args = "".join(f", {k}={v!r}" for k, v in values.items() if v is not None)
        return (f"# serial {serial} has no kexp.config.camera_id entry yet: add it to camera_frame, "
                f"then: self.img_{name} = self.image(cameras.{name}, t_offset=0.0{args})")
    new = DiagnosticImage(getattr(cameras, cam_key))
    new.key = f"img_{name}"
    return new.assignment(**values) + "  # rename it; t_offset (s) from where the sequence triggers it"


def install() -> None:
    from beacon.camera.viewer.widget import set_assignment_line_formatter
    set_assignment_line_formatter(diagnostic_assignment_line)
