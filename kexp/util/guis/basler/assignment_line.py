"""The camera viewer's "Copy assignment line" (right-click on Save), in this
lab's words: a ``DiagnosticCamera(...)`` line for kexp.config.camera_id's
``diagnostic_frame``, with the camera's current ROI, exposure and gain.

    self.z = DiagnosticCamera(cameras.z_basler, frames=['img_mot_beams_z', 'img_gm_beams_z'],
                              exposure_time=1.9e-05, gain=0.0, roi=[660, 300, 1260, 900])

``install()`` registers it with the viewer; the dashboards and
``camera_viewer_app`` call it at start-up.
"""


def _number(v):
    return float(f"{float(v):.4g}")


def diagnostic_assignment_line(info: dict) -> str:
    from kexp.config.camera_id import CameraParams, cameras, diagnostic_cameras

    serial = str(info.get("serial") or "")
    cam_key = next((k for k, v in vars(cameras).items()
                    if isinstance(v, CameraParams)
                    and str(getattr(v, "serial_no", "")) == serial), None)
    entry = next((e for e in diagnostic_cameras.entries() if e.camera.key == cam_key), None)
    name = entry.key if entry else (cam_key or str(info.get("name") or "camera").replace(" ", "_"))
    frames = list(entry.frames) if entry else [f"img_{cam_key or 'camera'}"]

    args = [f"cameras.{cam_key}" if cam_key else repr(serial), f"frames={frames!r}"]
    for k in ("exposure_time", "gain"):
        if info.get(k) is not None:
            args.append(f"{k}={_number(info[k])!r}")
    if info.get("roi") is not None:
        args.append(f"roi={[int(v) for v in info['roi']]!r}")
    if entry and entry.frame_settings:
        args.append(f"frame_settings={entry.frame_settings!r}")
    line = f"self.{name} = DiagnosticCamera(" + ", ".join(args) + ")"
    if not cam_key:
        line += f"  # serial {serial} has no kexp.config.camera_id entry yet"
    return line


def install() -> None:
    from beacon.camera.viewer.widget import set_assignment_line_formatter
    set_assignment_line_formatter(diagnostic_assignment_line)
