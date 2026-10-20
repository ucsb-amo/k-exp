"""scan()'s abort handler compiles inside a kexp experiment.

An exception that ends a scan first snapshots every channel in the kernel and
hands it to the host (waxx Scanner.scan -> _hand_over_abort_state), so an
aborted run can report its device state.  That code is in every experiment's
kernel; this compiles a minimal Base experiment's run() against the real
device db -- with the monitor's snapshot kernel, and with the no-op fallback
a run gets when it has no monitor.  No core-device connection is made (the
same thing artiq_compile does), and nothing is written outside pytest's temp
dir (the monitor's server client is a stub, the device-state file is
generated there).  Host behaviour is in waxx tests/test_abort_state.py.

Each compile takes ~5-10 s.  Skipped when %db% / %code% are not set.
"""
import json
import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

EXPT = '''
from artiq.experiment import *
from kexp import Base
import numpy as np

class AbortHandlerCompile(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self, setup_camera=False, suppress_live_od=True, save_data=False)
        self.xvar('t_tof', np.linspace(1.e-3, 2.e-3, 2))
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)
        delay(self.p.t_tof)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
'''


class _StubServerClient:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


class _NoDatasets:
    def __getattr__(self, name):
        raise RuntimeError(f"compile test: dataset access ({name})")


def _build(monkeypatch, tmp_path, with_monitor=True):
    from waxx.base import monitor as wmon
    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id

    state = str(tmp_path / "device_state.json")
    monkeypatch.setattr(wmon, "MonitorClient", _StubServerClient)
    if with_monitor:
        monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                            wmon.Monitor(expt, device_state_json_path=state))
    else:
        def _no_monitor(*a, **k):
            raise RuntimeError("compile test: no monitor")
        monkeypatch.setattr(kclients, "Monitor", _no_monitor)
    monkeypatch.setattr(kclients, "APDStageClient",
                        lambda *a, **k: SimpleNamespace(set_apd_stage=lambda *a, **k: None))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)
    monkeypatch.setattr(kclients, "BristolAverageReader",
                        lambda *a, **k: SimpleNamespace(get_average=lambda *a, **k: None))
    # finish_prepare asks the real SLM server whether a reinit is due (and
    # would ask it for one): never from a test.
    from waxx.control.slm.slm import SLM
    monkeypatch.setattr(SLM, "reinit_if_due",
                        lambda self, **kw: {"result": "compile test", "by": kw.get("by")})

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            raise RuntimeError("compile test: no wavemeter connection")

    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)

    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from artiq.language.environment import ProcessArgumentManager
    from artiq.tools import file_import, get_experiment

    path = tmp_path / "abort_handler_compile.py"
    path.write_text(EXPT)
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="compile_test_")
    cls = get_experiment(module)
    exp = cls((device_mgr, _NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return cls, exp, device_mgr


def _compile(cls, exp):
    # Never call run(): it would compile AND run on the core device.
    exp.core.compile(cls.run, [exp], {}, attribute_writeback=False, print_as_rpc=False)


def test_scan_with_the_monitor_snapshot_compiles(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path)
    try:
        assert exp._abort_snapshot_kernels is exp.monitor._snapshot_kernels
        assert len(exp._abort_snap_dds_f) == len(exp.monitor._snap_dds_keys)
        # the run-start SLM step ran (stubbed) and its record is kept for the file
        slm = json.loads(exp._extra_file_texts["slm_at_start"])
        assert slm["result"] == "compile test" and slm["by"].startswith("run start (")
        assert slm["uses_slm"] is False                      # an xy_basler run
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_the_handler_is_really_compiled(monkeypatch, tmp_path):
    """Negative control: a snapshot kernel that cannot compile fails the
    experiment's compile, so the two compiles here do type-check the handler."""
    from artiq.coredevice.core import CompileError
    from artiq.language.core import kernel_from_string
    from waxx.base.scanner import SNAPSHOT_PARAMS
    cls, exp, device_mgr = _build(monkeypatch, tmp_path)
    try:
        exp._abort_snapshot_kernels = [kernel_from_string(
            SNAPSHOT_PARAMS, "expt.no_such_frame_xyz.v = 1.")]
        with pytest.raises(CompileError, match="no_such_frame_xyz"):
            _compile(cls, exp)
    finally:
        device_mgr.close_devices()


def test_scan_without_a_monitor_compiles(monkeypatch, tmp_path):
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, with_monitor=False)
    try:
        assert not hasattr(exp, "monitor")
        assert len(exp._abort_snap_dds_f) == 1          # the no-op default
        _compile(cls, exp)
    finally:
        device_mgr.close_devices()
