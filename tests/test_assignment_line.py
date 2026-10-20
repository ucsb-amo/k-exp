"""The viewer's "Copy assignment line": image lines of kexp's diagnostic_frame."""
from waxx.control.cameras.diagnostic_frame import diagnostic_frame as diagnostic_frame_waxx

from kexp.config.camera_id import cameras, diagnostic_cameras
from kexp.util.guis.basler.assignment_line import diagnostic_assignment_line


def _info(serial, **kw):
    return {"serial": serial, "name": kw.pop("name", None), "camera_id": f"basler_usb:{serial}",
            "exposure_time": kw.pop("exposure_time", None), "gain": kw.pop("gain", None),
            "trigger_mode": kw.pop("trigger_mode", None), "roi": kw.pop("roi", None),
            "frame_tag": kw.pop("frame_tag", None)}


def _paste(text):
    """The lines run in a frame's __init__, as camera_id would run them."""
    class Frame(diagnostic_frame_waxx):
        def __init__(self):
            self.setup()
            exec(text.split("  #", 1)[0], {"cameras": cameras}, {"self": self})
            self.cleanup()
    return Frame()


def test_a_diagnostic_camera_gets_its_image_lines():
    text = diagnostic_assignment_line(_info("40416468", exposure_time=1.9e-05, gain=0.0,
                                            roi=[660, 300, 1260, 900]))
    assert text == (
        "self.img_mot_beams_z = self.image(cameras.z_basler, t_offset=0.005, exposure_time=1.9e-05, "
        "gain=0.0, roi=[660, 300, 1260, 900], label='MOT beams')\n"
        "self.img_gm_beams_z = self.image(cameras.z_basler, t_offset=0.00025, exposure_time=1.9e-05, "
        "gain=0.0, roi=[660, 300, 1260, 900], label='GM beams')")
    f = _paste(text)
    assert {k: i.settings() for k, i in f.images().items()} == {
        k: diagnostic_cameras.images()[k].settings() for k in ("img_mot_beams_z", "img_gm_beams_z")}


def test_the_shown_frame_gets_its_line_stage_and_rounding():
    """With a frame key shown alone, only that image's line; values rounded
    to 4 significant figures; t_stage, label and show kept."""
    roi = [1668, 1049, 2373, 1767]
    text = diagnostic_assignment_line(_info("40277706", exposure_time=0.0029999,
                                            gain=29.999998795594486, roi=roi, frame_tag="img_gm"))
    assert text == ("self.img_gm = self.image(cameras.mot_basler, t_offset=-0.025, exposure_time=0.003, "
                    "gain=30.0, roi=[1668, 1049, 2373, 1767], label='GM fluorescence', show='image')")
    assert _paste(text).img_gm.settings() == diagnostic_cameras.img_gm.settings()
    text = diagnostic_assignment_line(_info("40277706", exposure_time=0.00029999, gain=2.9999988,
                                            roi=roi, frame_tag="img_mot"))
    assert "t_stage='t_mot_load', exposure_time=0.0003, gain=3.0" in text
    # a key of another camera's frame: every image of this one
    lines = diagnostic_assignment_line(_info("40277706", roi=roi, frame_tag="img_mot_beams_z"))
    assert [ln.split(" =")[0] for ln in lines.splitlines()] == ["self.img_mot", "self.img_gm"]
    # the viewer knows no exposure / gain: the configured ones stay
    assert _paste(lines).img_gm.settings() == diagnostic_cameras.img_gm.settings()


def test_a_known_camera_without_images_and_an_unknown_serial(monkeypatch):
    # a fresh frame without the z basler's images (never the shared one: putting its
    # attributes back would change their order, which is the frame order)
    import kexp.config.camera_id as camera_id
    frame = camera_id.diagnostic_frame()
    for name in ("img_mot_beams_z", "img_gm_beams_z"):
        delattr(frame, name)
    monkeypatch.setattr(camera_id, "diagnostic_cameras", frame)
    text = diagnostic_assignment_line(_info("40416468", roi=[1, 2, 3, 4]))
    assert text == ("self.img_z_basler = self.image(cameras.z_basler, t_offset=0.0, roi=[1, 2, 3, 4])"
                    "  # rename it; t_offset (s) from where the sequence triggers it")
    assert _paste(text).img_z_basler.roi == [1, 2, 3, 4]
    unknown = diagnostic_assignment_line(_info("12345", name="new cam", gain=2.0))
    assert unknown == ("# serial 12345 has no kexp.config.camera_id entry yet: add it to camera_frame, "
                       "then: self.img_new_cam = self.image(cameras.new_cam, t_offset=0.0, gain=2.0)")
