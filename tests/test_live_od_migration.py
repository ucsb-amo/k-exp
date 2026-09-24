"""liveOD moved from kexp.util.live_od to waxx.util.live_od (2026-09-18). Every old
import path must keep working and give the SAME objects, waxx must not import
kexp, and the experiment process must stay light.

Nothing here opens a window, a socket or a camera. Never start the real
acquisition window in a test: it beacons onto the lab network.
"""
import importlib
import os
import pkgutil
import subprocess
import sys
import types

import pytest

OLD, NEW = "kexp.util.live_od", "waxx.util.live_od"

# old module (relative to OLD) -> public names that existed there before the move
COMPAT_SURFACE = {
    "": ["CameraMother", "CameraBaby", "CameraNanny", "DataHandler"],
    "live_od_client": ["LiveODClient", "CAM_READY_SLICE_S"],
    "live_od_server": ["LiveODServer"],
    "live_od_broadcaster": ["LiveODBroadcaster"],
    "camera_mother": ["CameraMother", "CameraBaby", "DataHandler", "SaveWorker", "CameraNanny",
                      "DATA_DIR", "RUN_ID_PATH", "nothing"],
    "camera_nanny": ["CameraNanny", "CHECK_EVERY", "CHECK_PERIOD", "N_NOTIFY", "nothing"],
    "camera_connection_widget": ["CamConnBar", "CameraButton", "ROISelector"],
    "shot_cross_section": ["ShotCrossSectionPairing", "cross_section_for_shot", "ATOM_NUMBER_KEYS"],
    "gui.main_window": ["LiveODWindow"],
    "gui.remote_viewer_window": ["RemoteViewerWindow", "LiveODSubscriber"],
    "gui.viewer": ["LiveODViewer", "SuppressPrints"],
    "gui.analyzer": ["Analyzer"],
    "gui.plotter": ["LiveODPlotter"],
    "gui.fk_tof_window": ["FkTofWindow", "_parse_time_input"],
    "gui.live_scalar_plot_window": ["LiveScalarPlotWindow", "METRICS"],
    "gui.adjust_panel": ["AdjustPanel", "AdjustParamRow", "AdjustSpecDialog",
                         "ScientificDoubleSpinBox", "ClickableLabel"],
}


def _modules(package_name):
    package = importlib.import_module(package_name)
    return sorted(info.name[len(package_name) + 1:]
                  for info in pkgutil.walk_packages(package.__path__, package_name + "."))


def test_every_waxx_module_has_an_old_path_and_vice_versa():
    new = set(_modules(NEW)) - {"config"}           # config is new; it never lived in kexp
    old = set(_modules(OLD))
    assert old == new, (old ^ new)


@pytest.mark.parametrize("module, names", sorted(COMPAT_SURFACE.items()))
def test_old_import_paths_give_the_same_objects(module, names):
    old = importlib.import_module(f"{OLD}.{module}".rstrip("."))
    new = importlib.import_module(f"{NEW}.{module}".rstrip("."))
    for name in names:
        assert hasattr(old, name), f"{old.__name__}.{name} is gone"
        if hasattr(new, name):                       # DATA_DIR / RUN_ID_PATH exist only on the old path
            assert getattr(old, name) is getattr(new, name), f"{name} is a copy, not the same object"


def test_pure_aliases_are_the_waxx_module_itself():
    """So that patching one patches the other, and sys.modules lookups by either
    name find the same module (the `art` timer relies on that)."""
    import kexp.util.live_od.live_od_client as old
    import waxx.util.live_od.live_od_client as new
    assert old is new
    assert sys.modules["kexp.util.live_od.live_od_client"] is new


def test_old_paths_still_work_when_loaded_by_file_path():
    import kexp.util.live_od as package
    path = os.path.join(os.path.dirname(package.__file__), "live_od_client.py")
    spec = importlib.util.spec_from_file_location("_loaded_by_path", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import waxx.util.live_od.live_od_client as new
    assert module.LiveODClient is new.LiveODClient


def _run(code):
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)


def test_waxx_live_od_never_imports_kexp():
    code = ("import importlib, pkgutil, sys; import waxx.util.live_od as p\n"
            "for info in pkgutil.walk_packages(p.__path__, p.__name__ + '.'):\n"
            "    importlib.import_module(info.name)\n"
            "sys.exit(1 if 'kexp' in sys.modules else 0)")
    result = _run(code)
    assert result.returncode == 0, result.stderr[-2000:]


def test_the_client_is_light_for_the_experiment_process_and_the_tools():
    code = ("import sys; from waxx.util.live_od.live_od_client import LiveODClient\n"
            "bad = [m for m in ('kexp', 'PyQt6', 'numpy', 'waxa', 'pylablib', 'scipy') if m in sys.modules]\n"
            "print(bad); sys.exit(1 if bad else 0)")
    result = _run(code)
    assert result.returncode == 0, result.stdout


def test_the_experiment_uses_the_waxx_client():
    import kexp.base.clients as clients
    assert clients.LiveODClient.__module__ == "waxx.util.live_od.live_od_client"


def test_the_window_refuses_to_start_without_a_lab_config(monkeypatch):
    """...and says how to start it, before any Qt object exists (no QApplication here)."""
    from waxx.util.live_od import config as live_od_config
    from waxx.util.live_od.gui.main_window import LiveODWindow
    monkeypatch.setattr(live_od_config, "_active", None)
    with pytest.raises(RuntimeError, match="launcher"):
        LiveODWindow()


def test_waxx_window_module_is_not_runnable_by_itself():
    result = _run("import runpy; runpy.run_module('waxx.util.live_od.gui.main_window', run_name='__main__')")
    assert result.returncode != 0 and "launcher" in result.stderr


def test_kexp_launchers_exist_and_point_at_waxx():
    import kexp.util.live_od.gui.main_window as launcher
    import waxx.util.live_od.gui.main_window as window
    assert callable(launcher.main) and launcher.LiveODWindow is window.LiveODWindow
    assert importlib.util.find_spec("waxx.util.live_od.gui.remote_viewer_window") is not None


# ---------------- the camera bar, built from the config (offscreen Qt, fake nanny) ----------------

@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_camera_bar_follows_the_config(qapp, monkeypatch):
    from PyQt6.QtWidgets import QPlainTextEdit
    from waxx.util.live_od import config as live_od_config
    from waxx.util.live_od.camera_connection_widget import CamConnBar

    cams = [types.SimpleNamespace(key=k) for k in ("cam_a", "cam_b", "cam_c")]
    opened = []
    nanny = types.SimpleNamespace(get_camera=lambda params: opened.append(params.key))
    monkeypatch.setattr(live_od_config, "_active",
                        live_od_config.LiveODConfig(camera_params_list=cams))

    bar = CamConnBar(nanny, QPlainTextEdit())
    assert [b.camera_name for b in bar.buttons] == ["cam_a", "cam_b", "cam_c"]
    assert bar.cam_b_button is bar.buttons[1] and bar.get_button("cam_c") is bar.buttons[2]
    assert bar.get_states() == {"cam_a": "closed", "cam_b": "closed", "cam_c": "closed"}
    assert opened == []                                 # nothing is opened at start by default
    assert [bar.layout.itemAt(0).layout().itemAt(i).widget() for i in range(3)] == bar.buttons


def test_kexp_camera_bar_is_the_five_k_machine_cameras(qapp, monkeypatch):
    """Through the real kexp config (saver stubbed: only an experiment working
    through liveOD may construct the real one)."""
    import waxa.data
    from PyQt6.QtWidgets import QPlainTextEdit
    from waxx.util.live_od import config as live_od_config
    from waxx.util.live_od.camera_connection_widget import CamConnBar
    from kexp.config import live_od as kexp_live_od

    monkeypatch.setattr(waxa.data, "DataSaver", lambda *a, **k: object())
    monkeypatch.setattr(live_od_config, "_active", kexp_live_od.make_live_od_config())
    opened = []
    bar = CamConnBar(types.SimpleNamespace(get_camera=lambda p: opened.append(p.key)), QPlainTextEdit())
    assert [b.camera_name for b in bar.buttons] == list(kexp_live_od.CAMERA_BAR_KEYS)
    assert len(bar.buttons) == 5 and opened == []
    for key in kexp_live_od.CAMERA_BAR_KEYS:            # the attribute names the old bar had
        assert getattr(bar, f"{key}_button") is bar.get_button(key)


def test_data_handler_takes_its_params_holder_and_camera_table_from_the_config(qapp, monkeypatch):
    from queue import Queue
    from waxx.util.live_od import config as live_od_config
    from waxx.util.live_od.camera_mother import DataHandler

    table = {"cam_a": types.SimpleNamespace(key="cam_a", magnification=3.0)}
    monkeypatch.setattr(live_od_config, "_active",
                        live_od_config.LiveODConfig(resolve_camera_params=table.get))
    handler = DataHandler(Queue(), "", save_data=False, imaging_type=0, camera_key="cam_a",
                          n_img=6, n_shots=2, n_pwa_per_shot=1)
    assert isinstance(handler.params, live_od_config.ImageCounts)
    assert (handler.params.N_img, handler.params.N_shots, handler.params.N_pwa_per_shot) == (6, 2, 1)
    handler.read_params()                               # no payload, no file: falls back to the table
    assert handler.camera_params is table["cam_a"]


# ---------------- the whole window, wired but not running ----------------

def test_the_window_builds_with_the_kexp_config_without_starting_anything(qapp, monkeypatch):
    """Constructs the real LiveODWindow with kexp's real config to exercise every
    widget and signal connection. Thread starts are replaced by no-ops, so no
    socket is bound, no beacon is sent and no camera is touched; the saver and the
    run-id source are stand-ins."""
    import waxa.data
    from waxx.util.live_od import config as live_od_config
    from waxx.util.live_od.gui import main_window as window_module
    from waxx.util.live_od.gui.plotter import LiveODPlotter
    from waxx.util.live_od.live_od_broadcaster import LiveODBroadcaster
    from waxx.util.live_od.live_od_server import LiveODServer
    from kexp.config import live_od as kexp_live_od

    started = []
    for cls in (LiveODServer, LiveODBroadcaster, LiveODPlotter):
        monkeypatch.setattr(cls, "start", lambda self, *a, _c=cls.__name__: started.append(_c))
    monkeypatch.setattr(waxa.data, "DataSaver", lambda *a, **k: object())

    config = kexp_live_od.make_live_od_config()
    config.run_id_source = types.SimpleNamespace(
        get_run_id=lambda: 12345, update_run_id=lambda *a, **k: None,
        check_for_mapped_data_dir=lambda *a, **k: True)
    monkeypatch.setattr(live_od_config, "_active", None)

    win = window_module.LiveODWindow(config)
    try:
        assert live_od_config.get_config() is config
        assert sorted(started) == ["LiveODBroadcaster", "LiveODPlotter", "LiveODServer"]
        assert [b.camera_name for b in win.camera_conn_bar.buttons] == list(kexp_live_od.CAMERA_BAR_KEYS)
        assert win.data_saver is config.data_saver and win.server_talk is config.run_id_source
        # the per-shot cross-section path is wired end to end
        assert win.analyzer._pairing._rule is config.cross_section_for_shot
        emitted = []
        win.analyzer.shot_scalars_signal.connect(emitted.append)
        win.analyzer.set_server(types.SimpleNamespace(get_requested_metrics=lambda: {"atom_number"}))
        win.analyzer.set_camera_params({"pixel_size_m": 4e-6, "magnification": 2.0})
        import numpy as np
        od = np.full((4, 4), 1.0)
        win.analyzer._emit_scalars(od, od.sum(axis=0), od.sum(axis=1))
        win.live_od_server.shot_conditions_signal.emit(0, {"i_outer_imaging": 180.0})
        qapp.processEvents()
        assert len(emitted) == 1 and emitted[0]["atom_cross_section_source"] == "high-field"
        # default ROI lookup goes through the config, not hard-coded camera names
        assert config.default_roi_id_for(kexp_live_od.CAMERA_BAR_KEYS[0]) == "basler_all"
    finally:
        win.run_id_timer.stop()
        win._camera_state_timer.stop()
        win.close()
