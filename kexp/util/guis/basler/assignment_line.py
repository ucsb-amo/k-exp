"""The camera viewer's "Copy assignment line" (right-click on Save), in this
lab's words: the camera's lines in kexp.config.camera_id's
``diagnostic_frame`` -- its ``self.camera(...)`` line with the camera's
current ROI, exposure and gain, then its images as they are configured (none
yet for a camera without an entry).

    self.z = self.camera(cameras.z_basler, exposure_time=1.9e-05, gain=0.0, roi=[660, 300, 1260, 900], label='z basler')
    self.img_mot_beams_z = self.image(self.z, t_offset=0.005, label='MOT beams')
    self.img_gm_beams_z = self.image(self.z, t_offset=0.00025, label='GM beams')

``install()`` registers it with the viewer; the dashboards and
``camera_viewer_app`` call it at start-up.
"""


def diagnostic_assignment_line(info: dict) -> str:
    from kexp.config.camera_id import CameraParams, DiagnosticCamera, cameras, diagnostic_cameras

    serial = str(info.get("serial") or "")
    cam_key = next((k for k, v in vars(cameras).items()
                    if isinstance(v, CameraParams)
                    and str(getattr(v, "serial_no", "")) == serial), None)
    entry = next((e for e in diagnostic_cameras.entries() if e.camera.key == cam_key), None)
    values = {k: info.get(k) for k in ("exposure_time", "gain", "roi")}
    if entry is not None:
        return entry.assignment(**values)

    name = cam_key or str(info.get("name") or "camera").replace(" ", "_")
    new = DiagnosticCamera(getattr(cameras, cam_key) if cam_key else serial)
    new.key = name
    line = new.assignment(**values)
    notes = []
    if not cam_key:
        notes.append(f"serial {serial} has no kexp.config.camera_id entry yet")
    notes.append(f"then: self.img_<name> = self.image(self.{name}, t_offset=<s>)")
    return line + "  # " + "; ".join(notes)


def install() -> None:
    from beacon.camera.viewer.widget import set_assignment_line_formatter
    set_assignment_line_formatter(diagnostic_assignment_line)
