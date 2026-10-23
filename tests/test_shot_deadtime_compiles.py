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


def _calls(nodes):
    """Dotted names of the calls in `nodes`, in source order."""
    import ast
    out = []
    for n in nodes:
        for c in ast.walk(n):
            if isinstance(c, ast.Call):
                f, parts = c.func, []
                while isinstance(f, ast.Attribute):
                    parts.append(f.attr)
                    f = f.value
                if isinstance(f, ast.Name):
                    parts.append(f.id)
                out.append((".".join(reversed(parts)), c))
    return sorted(out, key=lambda t: (t[1].lineno, t[1].col_offset))


def test_cleanup_makes_the_high_power_outputs_safe_before_anything_can_raise():
    """2026-10-23 (user: "fix cleanup hazard"; Reviewer B): cleanup_image_count
    can raise (wrong PWA count after a pre-imaging underflow; an underflow in the
    reference frames), and the raman DDS restore can raise. Neither may run
    before the coils are reset: the first statement wraps cleanup_image_count
    in a bare except that resets the coils (full path), switches the high-power
    outputs off and re-raises; the restore comes after reset_coils."""
    import ast
    import inspect
    import textwrap
    from kexp.base.base import Base

    fn = ast.parse(textwrap.dedent(inspect.getsource(Base.cleanup_scan_kernel))).body[0]
    first = fn.body[0]
    assert isinstance(first, ast.Try), "cleanup_image_count must be wrapped"
    assert [n for n, _ in _calls(first.body)] == ["self.cleanup_image_count"]
    (handler,) = first.handlers
    assert handler.type is None and handler.name is None          # bare except
    assert isinstance(handler.body[-1], ast.Raise) and handler.body[-1].exc is None
    names = [n for n, _ in _calls(handler.body)]
    for needed in ("self.reset_coils", "self.lightsheet.off", "self.tweezer.off",
                   "self.imaging.off", "self.raman.off", "self.ttl.raman_shutter.off"):
        assert needed in names, needed
    (rc,) = [c for n, c in _calls(handler.body) if n == "self.reset_coils"]
    kw = {k.arg: k.value for k in rc.keywords}
    assert isinstance(kw.get("trust_cached_state"), ast.Constant) and kw["trust_cached_state"].value is False

    rest = [n for n, _ in _calls(fn.body[1:])]
    assert rest.index("self.reset_coils") < rest.index("self.raman.clean_up_fast_frequency_update")


def test_a_short_image_count_after_a_failed_shot_does_not_raise():
    """2026-10-23 (organizer, from the MOT-preload analysis): after a shot that
    raised before its image (an underflow; Scanner's handler then runs the
    cleanup), cleanup_image_count resets the counters and warns instead of
    raising ValueError, so the cleanup reaches reset_coils and the underflow
    stays the reported exception. A shot that completed with a wrong count
    still raises."""
    import ast
    import inspect
    import textwrap
    from kexp.base.image import Image

    fn = ast.parse(textwrap.dedent(inspect.getsource(Image.cleanup_image_count))).body[0]
    src = ast.unparse(fn)
    assert "elif self.shot_completed:" in src
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert len(raises) == 1                     # only in the completed-shot branch
    # the counters are reset on every path
    assert src.rstrip().endswith("self._counter.img_idx = 0")


def test_the_per_shot_magnetometer_read_is_off_by_default_and_switchable():
    """2026-10-23 (user): the per-shot magnetometer read is off by default;
    data.b is then written 0. (= not read) every shot; Base(
    read_magnetometer_per_shot=True) restores the read exactly; the setting is
    recorded as p.do_read_magnetometer_per_shot."""
    import ast
    import inspect
    import textwrap
    from kexp.base.base import Base

    assert inspect.signature(Base.__init__).parameters["read_magnetometer_per_shot"].default is False
    init_src = inspect.getsource(Base.__init__)
    assert "self.params.do_read_magnetometer_per_shot = int(self.read_magnetometer_per_shot)" in init_src
    fn = ast.parse(textwrap.dedent(inspect.getsource(Base.init_scan_kernel))).body[0]
    ifs = [n for n in ast.walk(fn) if isinstance(n, ast.If)
           and ast.unparse(n.test) == "self.read_magnetometer_per_shot"]
    assert len(ifs) == 1
    (node,) = ifs
    assert [ast.unparse(s) for s in node.body] == ["self.read_magnetometer()"]
    assert [ast.unparse(s) for s in node.orelse] == ["self.data.b.put_data(0.0)"]
    # no other magnetometer read left in the shot start
    assert ast.unparse(fn).count("self.read_magnetometer()") == 1


def test_the_magnetometer_read_switched_on_compiles(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "EXPT", EXPT.replace(
        "save_data=False)", "save_data=False, read_magnetometer_per_shot=True)"))
    cls, exp, device_mgr = harness._build(monkeypatch, tmp_path)
    try:
        assert exp.read_magnetometer_per_shot is True
        assert exp.params.do_read_magnetometer_per_shot == 1
        harness._compile(cls, exp)
    finally:
        device_mgr.close_devices()
