"""The viewer's "Copy assignment line" in kexp's DiagnosticCamera form."""
from kexp.util.guis.basler.assignment_line import diagnostic_assignment_line


def _info(serial, **kw):
    return {"serial": serial, "name": kw.pop("name", None), "camera_id": f"basler_usb:{serial}",
            "exposure_time": kw.pop("exposure_time", None), "gain": kw.pop("gain", None),
            "trigger_mode": kw.pop("trigger_mode", None), "roi": kw.pop("roi", None)}


def test_a_diagnostic_camera_gets_its_entry_name_and_frames():
    line = diagnostic_assignment_line(_info("40416468", exposure_time=1.9e-05, gain=0.0,
                                            roi=[660, 300, 1260, 900]))
    assert line == ("self.z = DiagnosticCamera(cameras.z_basler, "
                    "frames=['img_mot_beams_z', 'img_gm_beams_z'], "
                    "exposure_time=1.9e-05, gain=0.0, roi=[660, 300, 1260, 900])")


def test_frame_settings_and_rounding_are_kept():
    line = diagnostic_assignment_line(_info("40320384", exposure_time=0.00029999,
                                            gain=29.999998795594486, roi=[1511, 141, 1729, 788]))
    assert line.startswith("self.x = DiagnosticCamera(cameras.x_basler, "
                           "frames=['img_tweezer_load_x', 'img_tweezer_evap_x'], "
                           "exposure_time=0.0003, gain=30.0, roi=[1511, 141, 1729, 788], "
                           "frame_settings={'img_tweezer_load_x': {'exposure_time': 5e-05, 'gain': 10.0}})")


def test_a_known_camera_without_a_diagnostic_entry_and_an_unknown_serial():
    assert diagnostic_assignment_line(_info("40277706", roi=[1, 2, 3, 4])) == (
        "self.mot = DiagnosticCamera(cameras.mot_basler, frames=['img_mot', 'img_gm'], roi=[1, 2, 3, 4], "
        "frame_settings={'img_gm': {'exposure_time': 0.003, 'gain': 30.0}})")
    unknown = diagnostic_assignment_line(_info("12345", name="new cam", gain=2.0))
    assert unknown.startswith("self.new_cam = DiagnosticCamera('12345', frames=['img_camera'], gain=2.0)")
    assert "no kexp.config.camera_id entry" in unknown
