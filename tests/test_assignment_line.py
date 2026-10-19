"""The viewer's "Copy assignment line": the camera's lines in kexp's diagnostic_frame."""
from waxx.control.cameras.diagnostic_frame import diagnostic_frame as diagnostic_frame_waxx

from kexp.config.camera_id import cameras, diagnostic_cameras
from kexp.util.guis.basler.assignment_line import diagnostic_assignment_line


def _info(serial, **kw):
    return {"serial": serial, "name": kw.pop("name", None), "camera_id": f"basler_usb:{serial}",
            "exposure_time": kw.pop("exposure_time", None), "gain": kw.pop("gain", None),
            "trigger_mode": kw.pop("trigger_mode", None), "roi": kw.pop("roi", None)}


def _paste(text):
    """The lines run in a frame's __init__, as camera_id would run them."""
    class Frame(diagnostic_frame_waxx):
        def __init__(self):
            self.setup()
            exec(text.split("  #", 1)[0], {"cameras": cameras}, {"self": self})
            self.cleanup()
    return Frame()


def test_a_diagnostic_camera_gets_its_lines():
    text = diagnostic_assignment_line(_info("40416468", exposure_time=1.9e-05, gain=0.0,
                                            roi=[660, 300, 1260, 900]))
    assert text == (
        "self.z = self.camera(cameras.z_basler, exposure_time=1.9e-05, gain=0.0, "
        "roi=[660, 300, 1260, 900], label='z basler')\n"
        "self.img_mot_beams_z = self.image(self.z, t=0.005, label='MOT beams')\n"
        "self.img_gm_beams_z = self.image(self.z, t=0.00025, label='GM beams')")
    f = _paste(text)
    assert f.z.frames == diagnostic_cameras.z.frames and f.z.label == "z basler"


def test_settings_stage_and_rounding_are_kept():
    text = diagnostic_assignment_line(_info("40277706", exposure_time=0.00029999,
                                            gain=2.999998795594486, roi=[1668, 1049, 2373, 1767]))
    assert text.splitlines()[0] == (
        "self.mot = self.camera(cameras.mot_basler, exposure_time=0.0003, gain=3.0, "
        "roi=[1668, 1049, 2373, 1767], label='MOT basler')")
    f = _paste(text)
    assert f.mot.frame_settings == diagnostic_cameras.mot.frame_settings
    assert [(i.key, i.t, i.t_stage, i.show) for i in f.mot.images] == \
        [(i.key, i.t, i.t_stage, i.show) for i in diagnostic_cameras.mot.images]


def test_a_known_camera_without_an_entry_and_an_unknown_serial(monkeypatch):
    for name in ("z", "img_mot_beams_z", "img_gm_beams_z"):
        monkeypatch.delattr(diagnostic_cameras, name)
    text = diagnostic_assignment_line(_info("40416468", roi=[1, 2, 3, 4]))
    assert text == ("self.z_basler = self.camera(cameras.z_basler, roi=[1, 2, 3, 4])"
                    "  # then: self.img_<name> = self.image(self.z_basler, t=<s>)")
    unknown = diagnostic_assignment_line(_info("12345", name="new cam", gain=2.0))
    assert unknown.startswith("self.new_cam = self.camera('12345', gain=2.0)  # serial 12345 has no")
    assert "self.image(self.new_cam, t=<s>)" in unknown
