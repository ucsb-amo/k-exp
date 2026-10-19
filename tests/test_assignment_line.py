"""The viewer's "Copy assignment line" in kexp's DiagnosticCamera form."""
from kexp.config.camera_id import DiagnosticCamera, DiagnosticImage, cameras, diagnostic_cameras
from kexp.util.guis.basler.assignment_line import diagnostic_assignment_line


def _info(serial, **kw):
    return {"serial": serial, "name": kw.pop("name", None), "camera_id": f"basler_usb:{serial}",
            "exposure_time": kw.pop("exposure_time", None), "gain": kw.pop("gain", None),
            "trigger_mode": kw.pop("trigger_mode", None), "roi": kw.pop("roi", None)}


def _eval(line):
    """The line's right-hand side, built as camera_id would build it."""
    rhs = line.split(" = ", 1)[1].split("  #", 1)[0]
    return eval(rhs, {"DiagnosticCamera": DiagnosticCamera, "DiagnosticImage": DiagnosticImage,
                      "cameras": cameras})


def test_a_diagnostic_camera_gets_its_entry_name_and_images():
    line = diagnostic_assignment_line(_info("40416468", exposure_time=1.9e-05, gain=0.0,
                                            roi=[660, 300, 1260, 900]))
    assert line == ("self.z = DiagnosticCamera(cameras.z_basler, "
                    "exposure_time=1.9e-05, gain=0.0, roi=[660, 300, 1260, 900], "
                    "images=[DiagnosticImage('img_mot_beams_z', at='mot_beams_on', t=0.005, "
                    "label='MOT beams'), "
                    "DiagnosticImage('img_gm_beams_z', at='gm_beams_on', t=0.00025, "
                    "label='GM beams')])")
    built = _eval(line)
    assert built.frames == diagnostic_cameras.z.frames and built.label == "z basler"


def test_frame_settings_label_and_rounding_are_kept():
    line = diagnostic_assignment_line(_info("40320384", exposure_time=0.00029999,
                                            gain=29.999998795594486, roi=[1511, 141, 1729, 788]))
    assert line.startswith("self.x = DiagnosticCamera(cameras.x_basler, "
                           "exposure_time=0.0003, gain=30.0, roi=[1511, 141, 1729, 788], images=[")
    built = _eval(line)
    assert built.frame_settings == diagnostic_cameras.x.frame_settings
    assert [(i.at, i.t, i.show) for i in built.images] == \
        [(i.at, i.t, i.show) for i in diagnostic_cameras.x.images]
    line = diagnostic_assignment_line(_info("40277703", gain=20.))
    assert "label='2D-MOT basler'" in line and _eval(line).label == "2D-MOT basler"


def test_a_known_camera_without_a_diagnostic_entry_and_an_unknown_serial(monkeypatch):
    monkeypatch.delattr(diagnostic_cameras, "z")
    line = diagnostic_assignment_line(_info("40416468", roi=[1, 2, 3, 4]))
    assert line == ("self.z_basler = DiagnosticCamera(cameras.z_basler, roi=[1, 2, 3, 4], images=[])"
                    "  # add DiagnosticImage(key, at=<hook>, t=<s>) entries")
    unknown = diagnostic_assignment_line(_info("12345", name="new cam", gain=2.0))
    assert unknown.startswith("self.new_cam = DiagnosticCamera('12345', gain=2.0, images=[])")
    assert "no kexp.config.camera_id entry" in unknown and "add DiagnosticImage" in unknown
