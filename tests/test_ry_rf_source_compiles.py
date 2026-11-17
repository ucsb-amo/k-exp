"""Rydberg beams driven by an RF consultant instead of a Siglent channel.

With RY_980_RF = 'rf_consultant' (kexp/base/devices.py) ry_980 is built on the
RF consultant assigned as ``rf_consultant_980``; every call an experiment makes on the beam
(sweep_to, set_frequency, init, set_siglent(frequency=...), post_scan's
return to default) must still compile.  Compile only -- no core-device
connection, no network (the consultant is not contacted until a call runs).
Isolation as in test_monitor_compiles.  Skipped without %db% / %code%.
"""
import os
import textwrap

import pytest

pytestmark = pytest.mark.skipif(not (os.environ.get("db") and os.environ.get("code")),
                                reason="needs the lab env vars %db% and %code%")

EXPT = '''
from artiq.experiment import *
from kexp import Base


class ry_rf_source_check(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self, setup_camera=False, suppress_live_od=True,
                      diagnostic_images=False)
        self.p.frequency_test_980 = 417.e6

    @kernel
    def run_kernel(self):
        self.core.reset()
        self.ry_980.sweep_to(self.p.frequency_test_980)
        self.ry_980.sweep_to(reset=True)
        self.ry_980.set_frequency(self.p.frequency_test_980)
        self.ry_980.set_siglent(frequency=self.p.frequency_test_980)
        self.ry_980.init(init_siglent=True)
        self.ry_405.sweep_to(reset=True)
'''


def _build(monkeypatch, tmp_path, ry_980_rf):
    import test_monitor_compiles as tmc  # its stubs: no monitor server, clients or wavemeter
    from artiq.language.environment import ProcessArgumentManager
    from artiq.master.databases import DeviceDB
    from artiq.master.worker_db import DeviceManager
    from artiq.tools import file_import, get_experiment

    import kexp.base.clients as kclients
    import kexp.config.wavemeter_id as wavemeter_id
    from types import SimpleNamespace
    from waxx.base import monitor as wmon
    monkeypatch.setattr(wmon, "MonitorClient", tmc._StubServerClient)
    state = str(tmp_path / "device_state.json")
    monkeypatch.setattr(kclients, "Monitor", lambda expt, device_state_json_path=None:
                        wmon.Monitor(expt, device_state_json_path=state))
    monkeypatch.setattr(kclients, "APDStageClient",
                        lambda *a, **k: SimpleNamespace(set_apd_stage=lambda *a, **k: None))
    monkeypatch.setattr(kclients, "HMRClient", kclients.HMRDummy)
    monkeypatch.setattr(kclients, "BristolAverageReader",
                        lambda *a, **k: SimpleNamespace(get_average=lambda *a, **k: None))

    class _NoWavemeter(wavemeter_id.WavemeterController):
        def __init__(self, *a, **k):
            raise RuntimeError("compile test: no wavemeter connection")
    monkeypatch.setattr(wavemeter_id, "WavemeterController", _NoWavemeter)

    path = tmp_path / "ry_rf_source_check.py"
    import kexp.base.devices as devices
    monkeypatch.setattr(devices, "RY_980_RF", ry_980_rf)
    path.write_text(textwrap.dedent(EXPT), encoding="utf-8")
    device_mgr = DeviceManager(DeviceDB(os.environ["db"]))
    module = file_import(str(path), prefix="compile_test_")
    cls = get_experiment(module)
    exp = cls((device_mgr, tmc._NoDatasets(), ProcessArgumentManager({}), {}))
    exp.prepare()
    return cls, exp, device_mgr


@pytest.mark.parametrize("ry_980_rf", ["rf_consultant", "siglent"])
def test_ry_980_calls_compile_with_either_source(monkeypatch, tmp_path, ry_980_rf):
    from waxx.control.misc.rf_consultant import RFConsultant
    cls, exp, device_mgr = _build(monkeypatch, tmp_path, ry_980_rf)
    try:
        on_rf = ry_980_rf == "rf_consultant"
        assert isinstance(exp.ry_980.rf_source, RFConsultant) == on_rf
        assert exp.ry_980.uses_rf_consultant == on_rf and not exp.ry_405.uses_rf_consultant
        assert exp.p.ry_980_rf_consultant == int(on_rf) and exp.p.ry_405_rf_consultant == 0
        exp.core.compile(cls.run_kernel, [exp], {}, attribute_writeback=False,
                         print_as_rpc=False)
    finally:
        device_mgr.close_devices()


def test_an_unknown_source_is_refused(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="RY_980_RF = 'rf' .devices.py.: use 'siglent' or 'rf_consultant'"):
        _build(monkeypatch, tmp_path, "rf")
