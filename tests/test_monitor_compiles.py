"""The monitor experiment -- with every composite op -- compiles.

Builds kexp/experiments/tools/monitor.py against the real device db and runs
ARTIQ's compiler on its run() kernel.  No core-device connection is made (the
same thing artiq_compile does), so this is safe to run anywhere the device db
is readable.  Run it after editing kexp.config.composite_devices: an op body is
ARTIQ code that is otherwise only compiled when the monitor starts on kong.

Isolation: the monitor's server client is a stub (no messages to the monitor
server), the device-state file is generated into pytest's temp dir by the
monitor's own reconcile, the stage and magnetometer clients are stubs and the
wavemeter frame falls back to the lab's DummyWavemeterController.

Each compile takes ~5 s.  Skipped when %db% / %code% are not set.
"""
import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")


class _StubServerClient:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


class _NoDatasets:
    def __getattr__(self, name):
        raise RuntimeError(f"compile test: dataset access ({name})")


def _build(monkeypatch, tmp_path, extra_devices=()):
    from waxx.base import monitor as wmon
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id
    import kexp.config.composite_devices as cd

    state = str(tmp_path / "device_state.json")
    monkeypatch.setattr(wmon, "MonitorClient", _StubServerClient)
    monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                        wmon.Monitor(expt, device_state_json_path=state))
    monkeypatch.setattr(kclients, "APDStageClient",
                        lambda *a, **k: SimpleNamespace(set_apd_stage=lambda *a, **k: None))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            raise RuntimeError("compile test: no wavemeter connection")

    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)
    if extra_devices:
        monkeypatch.setattr(cd, "COMPOSITE_DEVICES", cd.COMPOSITE_DEVICES + tuple(extra_devices))

    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from artiq.language.environment import ProcessArgumentManager
    from artiq.tools import file_import, get_experiment

    path = os.path.join(os.environ["code"], "k-exp", "kexp", "experiments", "tools", "monitor.py")
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(path, prefix="compile_test_")
    cls = get_experiment(module)
    exp = cls((device_mgr, _NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return cls, exp, device_mgr


def _compile(cls, exp):
    # run() is a host method that compiles AND runs run_kernel on the core
    # device -- never call it here.  Compile only.
    exp.core.compile(cls.run_kernel, [exp], {}, attribute_writeback=False, print_as_rpc=False)


def test_monitor_with_composite_ops_compiles(monkeypatch, tmp_path):
    from kexp.config.composite_devices import COMPOSITE_DEVICES
    from waxx.util.device_state.composite import OpTable
    cls, exp, device_mgr = _build(monkeypatch, tmp_path)
    try:
        assert exp.monitor._composites_enabled
        assert len(exp.monitor.op_kernels) == len(OpTable(COMPOSITE_DEVICES))
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_a_broken_op_fails_the_compile_and_the_fallback_compiles(monkeypatch, tmp_path):
    """Negative control: proves the compile above really type-checks op bodies.
    Then the monitor experiment's fallback (run() -> disable_composites ->
    compile again) must compile, so a broken op never takes the monitor down."""
    from artiq.coredevice.core import CompileError
    from waxx.util.device_state.composite import CompositeDevice, Op
    bad = CompositeDevice(key="negative_control", title="bad",
                          ops=(Op("bad", "bad", code="expt.raman.no_such_method()"),))
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, extra_devices=(bad,))
    try:
        with pytest.raises(CompileError, match="no_such_method"):
            _compile(cls, exp)
        exp.monitor.disable_composites("test")
        assert not exp.monitor.composites_enabled and len(exp.monitor.op_kernels) == 1
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_rejected_definitions_start_the_monitor_without_composites(monkeypatch, tmp_path):
    """Definitions that fail validation are caught in prepare()."""
    from waxx.util.device_state.composite import CompositeDevice, Op
    bad = CompositeDevice(key="negative_control", title="bad",
                          ops=(Op("bad", "bad", code="expt.x({undeclared})"),))
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, extra_devices=(bad,))
    try:
        assert not exp.monitor.composites_enabled
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()
