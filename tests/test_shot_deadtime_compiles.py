"""The shot dead-time changes compile inside a kexp experiment (2026-10-21).

* cleanup_scan_kernel -> reset_coils(trust_cached_state=self.shot_completed)
  -> igbt_magnet.cached_off / off_from_off (both coil classes);
* SLM.write_phase_mask_kernel (status-checked reuse), write_phase_mask_async
  and wait_phase_mask_settled.

Same harness as test_abort_state_compiles (no core-device connection, stubbed
servers, nothing written outside pytest's temp dir). Skipped when %db% /
%code% are not set. Each compile takes ~5-10 s.
"""
import os

import pytest

import test_abort_state_compiles as harness

pytestmark = harness.pytestmark

EXPT = '''
from artiq.experiment import *
from kexp import Base
import numpy as np

class ShotDeadtimeCompile(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self, setup_camera=False, suppress_live_od=True, save_data=False)
        self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)       # parallel (default)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, parallel=False,
                                         skip_if_unchanged=False)
        self.slm.write_phase_mask_async(phase=self.p.phase_slm_mask)
        self.inner_coil.snap_off()
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)
        delay(self.p.t_tof)
        self.slm.wait_phase_mask_settled()
        self.imaging.pulse(1.e-6)               # the guard inside the imaging beam
        delay(1.e-3)
        self.imaging.on()
        delay(1.e-6)
        self.imaging.off()
        delay(1.e-3)
        self.trigger_camera()                   # ... and before a camera trigger

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''


def test_scan_with_coil_skip_and_slm_paths_compiles(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "EXPT", EXPT)
    cls, exp, device_mgr = harness._build(monkeypatch, tmp_path)
    try:
        assert exp.shot_completed is False
        harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_the_full_reset_switch_compiles(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "EXPT", EXPT.replace(
        "save_data=False)", "save_data=False, fast_coil_reset=False)"))
    cls, exp, device_mgr = harness._build(monkeypatch, tmp_path)
    try:
        assert exp.fast_coil_reset is False
        assert exp.imaging.light_guard is exp.slm
        harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_a_wrong_coil_attribute_fails_the_compile(monkeypatch, tmp_path):
    """Negative control: the cleanup really is compiled with the new path."""
    from artiq.coredevice.core import CompileError
    from artiq.language.core import kernel_from_string
    from kexp.control import big_coil
    monkeypatch.setattr(big_coil.igbt_magnet, "cached_off", kernel_from_string(
        ["self"], "return self.no_such_coil_attribute_xyz == 0"))
    monkeypatch.setattr(harness, "EXPT", EXPT)
    cls, exp, device_mgr = harness._build(monkeypatch, tmp_path)
    try:
        with pytest.raises(CompileError, match="no_such_coil_attribute_xyz"):
            harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()
