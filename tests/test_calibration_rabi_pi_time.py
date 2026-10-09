"""kexp's calibration content: the rabi_pi_time analysis on synthetic flops, and
the K CalibrationConfig. Synthetic data only; the real params file is only
read (find / dry run), the ledger directory is never resolved."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from waxx.calibration.analysis import resolve, run_analysis
from waxx.calibration.record import evaluate

F_RABI = 75.0e3                       # Hz -> rate pi time 1/(2 f) = 6.6667 us
T_PI_TRUE = 1 / (2 * F_RABI)


def flop(seed=1, n_t=41, repeats=3, noise=30.0, t_max=20e-6):
    rng = np.random.default_rng(seed)
    t = np.repeat(np.linspace(0.0, t_max, n_t), repeats)
    y = 1000 + 400 * np.exp(-t / 60e-6) * np.cos(2 * np.pi * F_RABI * t) + rng.normal(0, noise, t.size)
    return t, y


def fake_ad(t, y, run_id=85600, xvarnames=("t_raman_pulse",)):
    return SimpleNamespace(xvarnames=list(xvarnames), xvars=[t], atom_number=y,
                           run_info=SimpleNamespace(run_id=run_id),
                           params=SimpleNamespace(t_raman_pi_pulse=6.6e-6, N_repeats=3))


def test_recovers_the_rate_pi_time_with_a_fit_uncertainty(tmp_path):
    from kexp.analysis.calibrations.rabi_pi_time import calibrate
    t, y = flop()
    fig = tmp_path / "t_raman_pi_pulse" / "85600.png"
    fig.parent.mkdir()
    r = calibrate(fake_ad(t, y), "t_raman_pi_pulse", figure_path=str(fig))
    assert r.fit["ok"], r.fit
    assert r.key == "t_raman_pi_pulse" and r.unit == "s" and r.run_id == 85600
    assert math.isfinite(r.unc) and r.unc > 0
    assert abs(r.value - T_PI_TRUE) < 4 * r.unc            # consistent with the truth
    assert abs(r.value / T_PI_TRUE - 1) < 0.03                 # gross sanity only
    assert r.fit["noise"] == "unweighted"                   # the default weighting
    # the uncertainty is the fit's: pi/omega * sigma_omega / omega
    om, dom = r.fit["params"]["omega"], r.fit["errors"]["omega"]
    assert r.unc == pytest.approx(np.pi / om * dom / om, rel=1e-12)
    assert r.value == pytest.approx(np.pi / om, rel=1e-12)
    assert r.n_used == t.size and r.excluded == {"count": 0, "reason": ""}
    assert {"chi2r", "dof", "aicc"} <= set(r.fit["goodness"])
    assert "t_pi_commanded" in r.fit["also"]                # reported, never written
    assert r.figure_path == str(fig) and fig.stat().st_size > 1000
    assert evaluate(r, {}) == []


def test_non_finite_shots_are_excluded_and_counted():
    from kexp.analysis.calibrations.rabi_pi_time import calibrate
    t, y = flop(seed=2)
    y[[5, 17]] = np.nan
    t[40] = np.inf
    r = calibrate(fake_ad(t, y), "t_raman_pi_pulse")
    assert r.fit["ok"]
    assert r.excluded == {"count": 3, "reason": "non-finite pulse length or atom_number"}
    assert r.n_used == t.size - 3


def test_failures_return_a_failed_result_not_a_number():
    from kexp.analysis.calibrations.rabi_pi_time import calibrate
    t, y = flop()
    two = fake_ad(t, y, xvarnames=("t_raman_pulse", "frequency"))
    r = calibrate(two, "t_raman_pi_pulse")
    assert r.fit["ok"] is False and "2-xvar run" in r.fit["reason"] and math.isnan(r.value)
    r = calibrate(fake_ad(t[:6], y[:6]), "t_raman_pi_pulse")          # 2 pulse lengths
    assert r.fit["ok"] is False and "Rabi fit failed" in r.fit["reason"] and r.unc is None
    r = calibrate(fake_ad(t, y), "t_raman_pi_pulse", bogus=1)
    assert r.fit["ok"] is False and "unknown option" in r.fit["reason"]
    r = calibrate(fake_ad(t, y[:-1]), "t_raman_pi_pulse")
    assert r.fit["ok"] is False and "do not match" in r.fit["reason"]
    assert [f["code"] for f in evaluate(r, {})] == ["analysis_failed", "nonfinite", "no_unc"]


def test_other_signal_by_attribute_path():
    from kexp.analysis.calibrations.rabi_pi_time import calibrate
    t, y = flop(seed=3)
    ad = fake_ad(t, np.zeros_like(y))
    ad.data = SimpleNamespace(apd=y)
    r = calibrate(ad, "t_raman_pi_pulse", signal="data.apd")
    assert r.fit["ok"] and abs(r.value - T_PI_TRUE) < 4 * r.unc and r.fit["signal"] == "data.apd"


def test_the_k_config(monkeypatch):
    """The K config and its registry. Importing kexp.analysis.calibrations runs
    kexp/analysis/__init__ (feedback, rabi_posterior), which imports the
    kexp.base MIXIN modules (class definitions; kexp.config.ip reads the device
    db file). Nothing is constructed: no Base, no device, no client, no
    connection. That import is what an experiment process already has."""
    from kexp.config import calibration as kcal_cfg
    cfg = kcal_cfg.CALIBRATION_CONFIG
    assert callable(cfg.ledger_dir)                         # resolved lazily, not here
    assert cfg.get_policy() == {}                           # no thresholds set
    fn = resolve("rabi_pi_time", cfg.registry_modules)
    assert fn.__module__ == "kexp.analysis.calibrations.rabi_pi_time"
    from kexp.config.expt_params import ExptParams
    assert cfg.get_params_class() is ExptParams
    # through the framework's budget runner
    t, y = flop(seed=4)
    r = run_analysis(fn, fake_ad(t, y), "t_raman_pi_pulse", budget_s=30, name="rabi_pi_time")
    assert r.fit["ok"] and r.analysis == "rabi_pi_time"
    # a lazily resolved ledger dir that is unset says so (no default location)
    import kexp.config.ip as ip
    monkeypatch.setattr(ip, "PATHS", (None,) + tuple(ip.PATHS[1:]))
    with pytest.raises(RuntimeError, match="data root"):
        cfg.get_ledger_dir()


def test_a_copy_of_the_real_params_file_takes_a_write_back(tmp_path, monkeypatch):
    """kexp's real ExptParams source, COPIED to tmp_path and imported from there
    under another name: find, dry run and a real apply + revert on the copy.
    The worktree's own kexp/config/expt_params.py is only read (to copy it)."""
    import importlib
    import sys
    from pathlib import Path
    import kexp
    from waxx.calibration import writeback
    from waxx.calibration.record import CalResult
    real = Path(kexp.__file__).parent / "config" / "expt_params.py"
    real_raw = real.read_bytes()
    copy = tmp_path / "kexp_params_copy_for_test.py"
    copy.write_bytes(real_raw)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    mod = importlib.import_module("kexp_params_copy_for_test")
    try:
        P = mod.ExptParams
        t = writeback.find_assignment("t_raman_pi_pulse", P)
        assert Path(t.file) == copy and t.method == "__init__"
        r = CalResult(key="t_raman_pi_pulse", value=3.91234e-06, unc=1.3e-08, run_id=1,
                      fit={"ok": True})
        rep = writeback.apply("t_raman_pi_pulse", r, P, dry_run=True, date="2026-10-09")
        assert rep.ok and not rep.written, rep.reason
        assert rep.new_line.strip() == "self.t_raman_pi_pulse = 3.9123e-06 #1, 2026-10-09"
        assert copy.read_bytes() == real_raw
        rep = writeback.apply("t_raman_pi_pulse", r, P, date="2026-10-09")
        assert rep.ok and rep.written, rep.reason
        assert mod.ExptParams().t_raman_pi_pulse == 3.9123e-06
        rep = writeback.revert("t_raman_pi_pulse", mod.ExptParams, date="2026-10-09")
        assert rep.ok, rep.reason
        assert mod.ExptParams().t_raman_pi_pulse == writeback.current_value(
            "t_raman_pi_pulse", mod.ExptParams)
    finally:
        sys.modules.pop("kexp_params_copy_for_test", None)
    assert real.read_bytes() == real_raw                     # the real file never changed


def test_base_hands_the_config_and_restarts_the_recorder():
    """Base.__init__ is neither run nor imported here (it builds devices and
    clients): its source is read from the file and checked for the two calls.
    The recorder is then exercised on kexp's ExptParams."""
    import ast
    from pathlib import Path
    import kexp
    src = (Path(kexp.__file__).parent / "base" / "base.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    base = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Base")
    init = next(n for n in base.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    body = ast.get_source_segment(src, init)
    assert "self.calibration_config = CALIBRATION_CONFIG" in body
    last = init.body[-1]
    assert ast.get_source_segment(src, last) == "self.start_param_override_recording()"
    from waxx.base.expt import Expt
    from kexp.config.expt_params import ExptParams
    p = ExptParams()
    p.compute_derived()                          # as Base's prepare_devices does
    e = SimpleNamespace(params=p, _param_overrides=None)
    Expt.start_param_override_recording(e)
    p.t_tof = 1.e-3
    p.compute_derived()
    Expt._stop_param_override_recording(e)
    assert e._param_overrides == frozenset({"t_tof"})


def test_end_of_run_emit_with_the_real_analysis(tmp_path, monkeypatch, capsys):
    """Expt's end-of-run emit (waxx) with kexp's rabi_pi_time on a synthetic
    flop: a stand-in run, a throwaway params module, a tmp ledger and a sandbox
    HDF5 run file. Prints the terminal output (pytest -s shows it)."""
    import importlib
    import json
    import sys
    import h5py
    import waxx.base.expt as expt_mod
    from waxx.base.expt import Expt
    from waxx.calibration import emit
    from waxx.calibration.config import CalibrationConfig

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv(emit.VETO_ENV, raising=False)
    monkeypatch.setattr(expt_mod, "_arm_exit_hang_dump", lambda *a, **k: None)
    (tmp_path / "e2e_params_mod.py").write_text(
        "class Params:\n    def __init__(self):\n"
        "        self.t_raman_pi_pulse = 6.6403e-06 #85412, 2026-10-07\n")
    importlib.invalidate_caches()
    pmod = importlib.import_module("e2e_params_mod")
    run_file = tmp_path / "sandbox_run_85600.h5"
    with h5py.File(run_file, "w") as f:
        f.attrs["run_complete"] = True
    t, y = flop(seed=7)
    ad = fake_ad(t, y)

    class Run:
        pass
    for name in ("calibrates", "_emit_calibrations"):
        setattr(Run, name, vars(Expt)[name])
    e = Run()
    e.params = pmod.Params()
    e.calibration_config = CalibrationConfig(
        ledger_dir=tmp_path / "ledger", policy="kexp.calibrations.writeback_policy",
        registry_modules=("kexp.analysis.calibrations",),
        loader=lambda rid, needs_images=False: ad)
    e._cal_declarations, e.calibration_results = [], []
    e.run_info = SimpleNamespace(save_data=1, run_id=85600, filepath=str(run_file))
    e.live_od_client = SimpleNamespace(last_end_run_reply={})
    e._run_saved, e._shot_complete_count, e._N_shots_total = True, t.size, t.size
    e._expt_file_stem = lambda: "raman_rabi_flop"
    try:
        e.calibrates("t_raman_pi_pulse", analysis="rabi_pi_time")
        e._emit_calibrations()
    finally:
        sys.modules.pop("e2e_params_mod", None)
    out = capsys.readouterr().out
    print(out)
    r = e.calibration_results[0]
    assert r.applied and abs(r.value - T_PI_TRUE) < 4 * r.unc
    assert out.splitlines()[0].startswith("[cal] t_raman_pi_pulse = ")
    assert "[cal] applied:" in out
    text = (tmp_path / "e2e_params_mod.py").read_text()
    assert "        # self.t_raman_pi_pulse = 6.6403e-06 #85412, 2026-10-07\n" in text
    assert (tmp_path / "ledger" / "t_raman_pi_pulse" / "85600.png").exists()
    with h5py.File(run_file, "r") as f:
        assert json.loads(f.attrs["calibration_emitted"])[0]["applied"] is True


def test_noise_option_passes_through():
    from kexp.analysis.calibrations.rabi_pi_time import calibrate
    t, y = flop(seed=5)
    r = calibrate(fake_ad(t, y), "t_raman_pi_pulse", noise="pooled")
    assert r.fit["ok"] and r.fit["noise"] == "pooled"


def test_figure_is_written_whole_and_images_only_when_needed(tmp_path):
    from kexp.analysis.calibrations.rabi_pi_time import calibrate
    from waxx.calibration.analysis import needs_images
    t, y = flop(seed=6)
    fig = tmp_path / "f.png"
    r = calibrate(fake_ad(t, y), "t_raman_pi_pulse", figure_path=str(fig))
    assert r.figure_path == str(fig) and fig.exists()
    assert sorted(x.name for x in tmp_path.iterdir()) == ["f.png"]      # no temp file left
    assert needs_images(calibrate, {}) is True                           # atom_number
    assert needs_images(calibrate, {"signal": "data.apd"}) is False
