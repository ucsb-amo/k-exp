import numpy as np
import pytest

import kexp.calibrations.tweezer_logpd as cal


def test_uncalibrated_raises():
    with pytest.raises(ValueError, match="not calibrated"):
        cal.power_to_vlogpd(1e-3)


@pytest.fixture
def calibrated(monkeypatch):
    # PDX10R-like made-up numbers: 0.3 V/decade, 2.05 V at 1 mW, floor 0.3 V (~1.5 nW)
    monkeypatch.setattr(cal, "LOGPD_V_PER_DECADE", 0.3)
    monkeypatch.setattr(cal, "LOGPD_V_AT_P_REF", 2.05)
    monkeypatch.setattr(cal, "LOGPD_V_FLOOR", 0.3)
    monkeypatch.setattr(cal, "LOGPD_V_SAT", np.nan)
    monkeypatch.setattr(cal, "LINEAR_SETPOINT_V_PER_W", 4000.)
    sgain, soffset = cal.choose_setpoint_map(2e-3)
    monkeypatch.setattr(cal, "SETPOINT_GAIN", sgain)
    monkeypatch.setattr(cal, "SETPOINT_OFFSET_V", soffset)
    return cal


def test_round_trip_and_ranges(calibrated):
    p = np.array([1e-5, 1e-3, 2e-3])
    v = cal.power_to_vlogpd(p)
    np.testing.assert_allclose(v, 2.05 + 0.3 * np.log10(p / 1e-3))
    np.testing.assert_allclose(cal.vlogpd_to_power(v), p)
    assert cal.v_setpoint_min() == pytest.approx(0.9)  # floor + 2 decades
    with pytest.raises(ValueError, match="below vset_min"):
        cal.power_to_vlogpd(1e-7)
    with pytest.raises(ValueError, match="ADC range"):
        cal.power_to_vlogpd(0.1)                        # 2.65 V > 2.5 V
    with pytest.raises(ValueError, match="no zero"):
        cal.power_to_vlogpd(0.)


def test_log_setpoint_map(calibrated):
    s = cal.power_to_log_setpoint(np.array([0., 1e-5, 2e-3]))
    assert s[0] == 0.
    assert s[2] == pytest.approx(9.5)
    c = cal.firmware_constants(smode=0)
    # firmware: target = soffset + sgain * s must equal the PD voltage for that power ...
    assert c["soffset"] + c["sgain"] * s[1] == pytest.approx(cal.power_to_vlogpd(1e-5))
    # ... and 0 V must be off
    assert c["soffset"] < c["vset_min"] - c["hyst"]


def test_offset_that_would_turn_on_at_zero_refused(calibrated, monkeypatch):
    monkeypatch.setattr(cal, "SETPOINT_OFFSET_V", cal.v_setpoint_min())
    with pytest.raises(ValueError, match="ON at low power"):
        cal.power_to_log_setpoint(1e-3)
    with pytest.raises(ValueError, match="ON at low power"):
        cal.firmware_constants(smode=0)


def test_linear_setpoint_and_firmware_constants(calibrated):
    s = cal.power_to_linear_setpoint(np.array([0., 1e-3, 2e-3]))
    np.testing.assert_allclose(s, [0., 4., 8.])
    with pytest.raises(ValueError, match="below vset_min"):
        cal.power_to_linear_setpoint(1e-7)
    c = cal.firmware_constants(smode=1)
    p = 3e-4
    target = c["vref"] + c["klog"] * np.log10(cal.power_to_linear_setpoint(p) / c["sref"])
    assert target == pytest.approx(cal.power_to_vlogpd(p))


def test_negative_slope_refused(calibrated, monkeypatch):
    monkeypatch.setattr(cal, "LOGPD_V_PER_DECADE", -0.3)
    with pytest.raises(ValueError, match="rising"):
        cal.power_to_vlogpd(1e-3)
