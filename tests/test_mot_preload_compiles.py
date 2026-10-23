"""MOT pre-load (Base(mot_preload=...), 2026-10-23): compiles, refuses what it
cannot do, records itself, and reads the field at a recorded delay.

* the scan with the pre-load ON and OFF compiles (warm-ups, cleanup with the
  end-of-shot field read and mot_preload_on, mot()'s bookkeeping, post_scan,
  cleanup_abort_kernel, the scan loop's new safe-state handlers);
* finish_prepare refuses a hand-set p.do_mot_preload and a scanned one;
* the run's root text 'mot_preload' says what the pre-load does;
* Control._read_magnetometer_after picks the first sample completed late
  enough and records its delay (a fake client: no network).

Same harness as test_abort_state_compiles (no core-device connection,
stubbed servers, nothing written outside pytest's temp dir). Skipped when
%db% / %code% are not set (the host-only test at the bottom always runs).
"""
import json
import time
from types import SimpleNamespace

import pytest

import test_abort_state_compiles as harness

EXPT = '''
from artiq.experiment import *
from kexp import Base
import numpy as np

class MotPreloadCompile(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self, setup_camera=False, suppress_live_od=True, save_data=False,
                      warmup_shots=1, mot_preload=True)
        self.p.t_mot_load = 0.2
        self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.mot(self.p.t_mot_load)
        self.release()
        delay(self.p.t_tof)

    @kernel
    def warmup_kernel(self):
        self.mot(self.p.t_mot_load)
        self.release()
        delay(self.p.t_tof)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
'''


@harness.pytestmark
def test_scan_with_the_preload_compiles(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "EXPT", EXPT)
    cls, exp, device_mgr = harness._build(monkeypatch, tmp_path)
    try:
        assert exp.mot_preload is True and exp.p.do_mot_preload == 1
        rec = json.loads(exp._extra_file_texts["mot_preload"])
        assert rec["enabled"] is True and "END of the shot" in rec["data_b"]
        assert len(exp.data.mot_preload.shot_data) == 3
        harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()


@harness.pytestmark
def test_scan_without_the_preload_compiles(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "EXPT", EXPT.replace(", mot_preload=True)", ")"))
    cls, exp, device_mgr = harness._build(monkeypatch, tmp_path)
    try:
        assert exp.mot_preload is False and exp.p.do_mot_preload == 0
        assert json.loads(exp._extra_file_texts["mot_preload"]) == {"enabled": False}
        harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()


@harness.pytestmark
def test_a_hand_set_parameter_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "EXPT", EXPT.replace(
        ", mot_preload=True)", ")").replace(
        "self.p.t_mot_load = 0.2", "self.p.t_mot_load = 0.2\n        self.p.do_mot_preload = 1"))
    with pytest.raises(ValueError, match="Base argument"):
        harness._build(monkeypatch, tmp_path)


@harness.pytestmark
def test_a_scanned_preload_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "EXPT", EXPT.replace(
        "self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))",
        "self.xvar('do_mot_preload', [0, 1])"))
    with pytest.raises(ValueError, match="cannot be scanned"):
        harness._build(monkeypatch, tmp_path)


@harness.pytestmark
def test_the_preload_is_really_compiled(monkeypatch, tmp_path):
    """Negative control: a broken mot_preload_on fails the compile."""
    from artiq.coredevice.core import CompileError
    from artiq.language.core import kernel_from_string
    from kexp.base import cooling
    monkeypatch.setattr(cooling.Cooling, "mot_preload_on", kernel_from_string(
        ["self"], "self.no_such_preload_attribute_xyz = 1"))
    monkeypatch.setattr(harness, "EXPT", EXPT)
    cls, exp, device_mgr = harness._build(monkeypatch, tmp_path)
    try:
        with pytest.raises(CompileError, match="no_such_preload_attribute_xyz"):
            harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()


# ---- host only: the end-of-shot field read (one GET, no wait) -------------

class _FakeMagnetometer:
    """Serves its latest sample: one every `period` s, the first `age` s old."""

    def __init__(self, period=0.12, age=0.2):
        self.t0 = time.time() - age
        self.period = period
        self.n_get = 0

    def _get_field(self, timeout=0.5):
        self.n_get += 1
        n = int((time.time() - self.t0) / self.period)
        t = self.t0 + n * self.period
        return {"ok": True, "t": t, "Btot": 0.5 + 0.001 * n}


def _fake_self(mag):
    return SimpleNamespace(magnetometer=mag, _magnetometer_skipped=False,
                           _magnetometer_fails=0, _read_magnetometer=lambda: 0.)


def test_the_field_read_takes_the_latest_sample_and_records_its_delay():
    from kexp.base.control import Control
    mag = _FakeMagnetometer(period=0.12, age=0.5)
    t0 = time.time()
    b, delay = Control._read_magnetometer_after(_fake_self(mag), 0.175)   # outer ended 175 ms ago
    assert mag.n_get == 1 and time.time() - t0 < 0.1                      # one GET, no wait
    assert b > 0.5
    assert 0.175 - 0.12 - 0.01 <= delay <= 0.175 + 0.01                   # latest sample 0-120 ms old


def test_a_sample_older_than_the_discharge_end_is_recorded_negative():
    from kexp.base.control import Control
    mag = _FakeMagnetometer(period=10., age=0.3)                          # latest sample 0.3 s old
    b, delay = Control._read_magnetometer_after(_fake_self(mag), 0.1)
    assert b == pytest.approx(0.5) and delay == pytest.approx(-0.2, abs=0.02)


def test_a_failed_field_read_records_zero_and_nan():
    import math
    from kexp.base.control import Control

    class _Dead:
        def _get_field(self, timeout=0.5):
            raise OSError("no server")

    me = _fake_self(_Dead())
    b, delay = Control._read_magnetometer_after(me, 0.01)
    assert b == 0. and math.isnan(delay) and me._magnetometer_fails == 1
