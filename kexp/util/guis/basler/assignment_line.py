"""The camera viewer's "Copy assignment line" (right-click on Save), in this
lab's words: a ``DiagnosticCamera(...)`` line for kexp.config.camera_id's
``diagnostic_frame``, with the camera's current ROI, exposure and gain and
the images its entry takes (none for a camera without one yet).

    self.z = DiagnosticCamera(cameras.z_basler, exposure_time=1.9e-05, gain=0.0, roi=[660, 300, 1260, 900], label='z basler', images=[DiagnosticImage('img_mot_beams_z', at='mot_beams_on', t=0.005, label='MOT beams'), ...])

``install()`` registers it with the viewer; the dashboards and
``camera_viewer_app`` call it at start-up.
"""


def _number(v):
    return float(f"{float(v):.4g}")


def diagnostic_assignment_line(info: dict) -> str:
    from kexp.config.camera_id import CameraParams, DiagnosticCamera, cameras, diagnostic_cameras

    serial = str(info.get("serial") or "")
    cam_key = next((k for k, v in vars(cameras).items()
                    if isinstance(v, CameraParams)
                    and str(getattr(v, "serial_no", "")) == serial), None)
    entry = next((e for e in diagnostic_cameras.entries() if e.camera.key == cam_key), None)
    name = entry.key if entry else (cam_key or str(info.get("name") or "camera").replace(" ", "_"))

    args = [f"cameras.{cam_key}" if cam_key else repr(serial)]
    for k in ("exposure_time", "gain"):
        if info.get(k) is not None:
            args.append(f"{k}={_number(info[k])!r}")
    if info.get("roi") is not None:
        args.append(f"roi={[int(v) for v in info['roi']]!r}")
    if entry and entry.label != DiagnosticCamera(entry.camera).label:
        args.append(f"label={entry.label!r}")
    args.append(f"images={entry.images!r}" if entry else "images=[]")
    line = f"self.{name} = DiagnosticCamera(" + ", ".join(args) + ")"
    notes = []
    if not cam_key:
        notes.append(f"serial {serial} has no kexp.config.camera_id entry yet")
    if not entry:
        notes.append("add DiagnosticImage(key, at=<hook>, t=<s>) entries")
    if notes:
        line += "  # " + "; ".join(notes)
    return line


def install() -> None:
    from beacon.camera.viewer.widget import set_assignment_line_formatter
    set_assignment_line_formatter(diagnostic_assignment_line)
