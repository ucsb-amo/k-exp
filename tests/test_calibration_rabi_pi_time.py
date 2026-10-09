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
    assert abs(r.value / T_PI_TRUE - 1) < 0.01
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
    assert r.fit["ok"] and abs(r.value / T_PI_TRUE - 1) < 0.01 and r.fit["signal"] == "data.apd"


def test_the_k_config(monkeypatch):
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


def test_the_real_params_line_is_a_valid_target_read_only():
    """find + dry run on kexp's own ExptParams: reads the file, writes nothing."""
    from pathlib import Path
    from waxx.calibration import writeback
    from waxx.calibration.record import CalResult
    from kexp.config.expt_params import ExptParams
    t = writeback.find_assignment("t_raman_pi_pulse", ExptParams)
    assert Path(t.file).name == "expt_params.py" and t.method == "__init__"
    raw = Path(t.file).read_bytes()
    r = CalResult(key="t_raman_pi_pulse", value=3.91234e-06, unc=1.3e-08, run_id=1,
                  fit={"ok": True})
    rep = writeback.apply("t_raman_pi_pulse", r, ExptParams, dry_run=True, date="2026-10-09")
    assert rep.ok and not rep.written, rep.reason
    assert rep.new_line.strip() == "self.t_raman_pi_pulse = 3.9123e-06 #1, 2026-10-09"
    assert Path(t.file).read_bytes() == raw


def test_base_hands_the_config_and_restarts_the_recorder():
    """Base.__init__ is not run here (it builds devices); its source is checked
    for the two calls instead, and the recorder works on kexp's ExptParams."""
    import inspect
    from kexp.base.base import Base
    src = inspect.getsource(Base.__init__)
    assert "self.calibration_config = CALIBRATION_CONFIG" in src
    assert src.rstrip().endswith("self.start_param_override_recording()")
    from waxx.base.expt import Expt
    from kexp.config.expt_params import ExptParams
    p = ExptParams()
    e = SimpleNamespace(params=p, _param_overrides=None)
    Expt.start_param_override_recording(e)
    p.t_tof = 1.e-3
    p.compute_derived()
    Expt._stop_param_override_recording(e)
    assert e._param_overrides == frozenset({"t_tof"})
