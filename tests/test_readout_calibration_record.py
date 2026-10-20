"""The host record of the interleaved readout calibration
(kexp.base.readout_calibration) on a stub experiment and a stub sub-scan:
pair logging, the end-of-run windows per readout mode, the rules, and that a
failing estimator leaves a logged window, never an exception."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

import kexp.base.readout_calibration as rc

T_PI, T_OFF = 3.78e-6, 127e-9
V_UP, V_DOWN, SIG = -0.080, -0.150, 0.007


def _sub(n_events=6, n_reads=5, modes=(0., 1.), seed=0, drop=()):
    """A finished sub-scan's host state: pairs (up, down), modes cycling,
    reads near the endpoints with noise, status 1 except ``drop`` slots."""
    rng = np.random.default_rng(seed)
    N = 2 * n_events
    t = np.tile([0., T_PI + T_OFF], n_events)
    mode = np.repeat([modes[e % len(modes)] for e in range(n_events)], 2)
    truth = np.where(np.isclose(t, 0.), V_UP, V_DOWN)
    apd = truth[:, None] + rng.normal(0., SIG, (N, n_reads))
    status = np.ones(N, dtype=np.int32)
    for s in drop:
        status[s] = 2
        apd[s] = 0.
    tm = 1000. + 6. * np.arange(N)
    d = SimpleNamespace(apd=SimpleNamespace(_run_data=apd), status=SimpleNamespace(_run_data=status),
                        time=SimpleNamespace(_run_data=tm), cal_readout_mode=SimpleNamespace(_run_data=mode))
    sub = SimpleNamespace(data=d, scan_xvars=[SimpleNamespace(values=t)], n_points_per_event=2,
                          log={"points": [], "notes": []})
    return sub


def _expt(**over):
    p = SimpleNamespace(v_apd_all_up=-0.0748, v_apd_all_down=-0.1555, n_photons_per_shot=1171.45,
                        std_n_photons_per_shot=159.58, feedback_measurement_midpoint_fraction=0.5,
                        t_raman_pi_pulse=T_PI, t_raman_pulse_offset=T_OFF)
    for k, v in over.items():
        setattr(p, k, v)
    return SimpleNamespace(p=p)


def test_pairs_are_logged_as_they_complete_and_windows_per_mode_at_the_end():
    sub = _sub(n_events=8)
    rec = rc.ReadoutCalibrationRecord(_expt(), sub, n_boot=20)
    assert sub.log["start"]["values"]["v_apd_all_up"] == -0.0748
    assert sub.log["decision_policy"].startswith("evaluated_only")
    for i in range(16):
        rec.on_point(i, True)
    pairs = sub.log["pairs"]
    assert len(pairs) == 8 and [p["mode"] for p in pairs] == [0., 1.] * 4
    assert all(abs(p["contrast"] - (V_UP - V_DOWN)) < 0.02 for p in pairs)
    assert pairs[0]["order"] == "up_first" and pairs[0]["slots"] == [0, 1]
    rec.finish_run()
    w = sub.log["windows"]
    assert [x["mode"] for x in w] == [0., 1.] and all(x["status"] == "evaluated_only" for x in w)
    for x in w:
        e = x["estimate"]
        assert x["n_up"] == 4 and x["n_down"] == 4
        assert abs(e["v_up"] - V_UP) < 4 * e["v_up_err"] and abs(e["v_down"] - V_DOWN) < 4 * e["v_down_err"]
        assert e["n_photons_new"] == pytest.approx(1171.45 * e["contrast"] / (-0.0748 + 0.1555), rel=1e-9)
        assert e["std_n_new"] == pytest.approx(e["n_photons_new"] * e["sigma_v"] / e["contrast"], rel=1e-9)
        assert x["decision"] == "evaluated_only" and x["constants_in_force"]["t_raman_pi_pulse"] == T_PI
        assert x["sane"] and x["sanity_failures"] == []
        assert x["groups"]["up"]["flag"] is False and x["groups"]["down"]["flag"] is False
    s = sub.log["eval_summary"]
    assert s["n_pairs_logged"] == 8 and s["n_evaluated"] == 2 and s["n_failed"] == 0 and s["n_sane"] == 2
    json.dumps(sub.log, default=float)


def test_a_moved_readout_is_suspicious_and_a_small_contrast_fails_sanity():
    sub = _sub(n_events=8, modes=(0.,))
    rec = rc.ReadoutCalibrationRecord(_expt(v_apd_all_up=-0.100, v_apd_all_down=-0.130), sub, n_boot=20)
    rec.finish_run()
    (w,) = sub.log["windows"]
    assert w["suspicious"] and any("V_up moved" in r for r in w["suspicious_reasons"])
    assert any("contrast changed" in r for r in w["suspicious_reasons"])
    sub2 = _sub(n_events=8, modes=(0.,))
    sub2.data.apd._run_data[:] = -0.10 + 0.002 * (sub2.data.apd._run_data + 0.1)   # ~0 contrast
    rec2 = rc.ReadoutCalibrationRecord(_expt(), sub2, n_boot=20)
    rec2.finish_run()
    (w2,) = sub2.log["windows"]
    assert not w2["sane"] and any("contrast" in r and "below" in r for r in w2["sanity_failures"])


def test_failed_points_are_left_out_and_too_few_points_say_so():
    sub = _sub(n_events=3, modes=(0.,), drop=(2, 5))
    rec = rc.ReadoutCalibrationRecord(_expt(), sub, n_boot=20, min_pairs=3)
    for i in range(6):
        rec.on_point(i, i not in (2, 5))
    assert sub.log["pairs"][1]["n_ok"] == 1 and sub.log["pairs"][1]["v_up"] is None
    rec.finish_run()
    (w,) = sub.log["windows"]
    assert w["status"] == "too_few_points" and w["n_up"] == 2 and w["n_down"] == 2 and w["n_left_out"] == 2


def test_an_estimator_that_raises_leaves_a_failed_window_and_never_raises(monkeypatch, capsys):
    import waxa.analysis.readout as ro
    sub = _sub(n_events=4, modes=(0.,))
    rec = rc.ReadoutCalibrationRecord(_expt(), sub, n_boot=20)

    def boom(*a, **k):
        raise RuntimeError("estimator broke")

    monkeypatch.setattr(ro, "calibrate_readout", boom)
    rec.finish_run()
    (w,) = sub.log["windows"]
    assert w["status"] == "failed" and "estimator broke" in w["error"]
    assert sub.log["eval_summary"]["n_failed"] == 1
    assert "evaluation of mode 0 failed" in capsys.readouterr().out


def test_start_constants_carry_their_params_file_tags():
    from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams
    p = ExptParams()
    import re
    tags = rc._tags_from_params_file(p, rc.FIELDS)
    # the active line's tag: "<run id>, <date>  # <note>, <source>"
    assert re.match(r"\d{5}, 20\d\d-\d\d-\d\d", tags["v_apd_all_up"]), tags
    assert re.match(r"\d{5}, 20\d\d-\d\d-\d\d", tags["v_apd_all_down"]), tags
