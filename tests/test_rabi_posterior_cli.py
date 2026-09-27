"""Offline tests for kexp.analysis.rabi_posterior_cli on synthetic pulse trains.

Every run here is generated from the forward model (evolve_pulse_train) with a
known truth, so the gates can be checked against what they are supposed to
catch: a clean scanned-duration run passes; a stale APD calibration fails the
fixed-calibration verdict but not the joint one; an inverted readout, drift
inside the run, and an APD that sees no light each fail their own gate;
never-taken and non-finite shots are excluded and counted.

Nothing here touches the data drive, a server or the network: runs are built
in memory and main() is driven with an injected loader and a tmp_path --out.

    .venv/Scripts/python.exe -m pytest k-exp/tests/test_rabi_posterior_cli.py -q
"""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from kexp.analysis import rabi_posterior_cli as cli
from kexp.analysis.rabi_posterior import (RabiCalibration, evolve_pulse_train,
                                          expected_photon_fraction)

T_PI = 6.5821e-6
F_TRUE = 1.0 / (2.0 * T_PI)
LS, COH, MID = 40.61e3, 0.62, 0.47
V_DOWN, V_RANGE, SIGMA_V = -0.212, 0.040, 0.0085
V_DARK = -0.231
OVERHEAD = 30.6e-6
FRACS = np.array([0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.1, 1.35, 1.6, 1.9])
N_PULSE = 15


def true_cal(**over):
    cal = RabiCalibration(t_img_pulse=5e-6, frequency_lightshift=LS, back_action_coherence=COH,
                          feedback_measurement_midpoint_fraction=MID,
                          v_apd_all_down=V_DOWN, v_apd_all_up=V_DOWN + V_RANGE,
                          n_photons_per_shot=1000.0,
                          std_n_photons_per_shot=SIGMA_V / V_RANGE * 1000.0,
                          t_turn_on_delay=127e-9, t_raman_pi_pulse=T_PI)
    return replace(cal, **over)


def make_run(n_rep=4, seed=0, drift_frac=0.0, invert=False, no_light=False, cal=None,
             run_id=990001, t0_true=127e-9):
    """Scanned-duration run in C order (row = duration cell), taken shuffled per repeat."""
    rng = np.random.default_rng(seed)
    n_d = FRACS.size
    t_rows = np.repeat(FRACS * T_PI, n_rep)                 # row r -> duration FRACS[r // n_rep]
    t_eff = np.round(np.tile(t_rows[:, None], (1, N_PULSE)) * 1e9) * 1e-9
    n_shot = t_eff.shape[0]
    # acquisition: repeat block k visits every duration once, in random order
    acq = np.concatenate([rng.permutation(n_d) * n_rep + k for k in range(n_rep)])
    pos = np.empty(n_shot, dtype=int)
    pos[acq] = np.arange(n_shot)                             # acquisition position of each row
    f_row = np.where(pos >= n_shot // 2, F_TRUE * (1.0 + drift_frac), F_TRUE)

    tc = true_cal(t_turn_on_delay=t0_true)
    v = np.empty_like(t_eff)
    for f in np.unique(f_row):
        m = f_row == f
        s_z, _ = evolve_pulse_train(t_eff[m] - tc.t_turn_on_delay, t_eff[m], np.array([f]), tc)
        g = expected_photon_fraction(s_z[:, :, 0], MID, True)
        v[m] = (V_DOWN + V_RANGE - V_RANGE * g) if invert else (V_DOWN + V_RANGE * g)
    if no_light:
        v = np.full_like(v, V_DARK)
    v = v + rng.normal(0.0, SIGMA_V if not no_light else 1e-3, size=v.shape)

    t_rec = np.concatenate([np.zeros((n_shot, 1)),
                            np.cumsum(t_eff[:, :-1] + OVERHEAD, axis=1)], axis=1)
    ref = np.column_stack([np.full(n_shot, V_DOWN + 0.5 * V_RANGE), np.full(n_shot, V_DARK)])
    ref = ref + rng.normal(0.0, 1e-3, size=ref.shape)
    return cli.run_data_from_arrays(run_id, v, t_eff, cal or true_cal(), t_rec=t_rec,
                                    apd_reference=ref, acq_order=acq,
                                    acq_order_source="synthetic shuffled",
                                    meta={"imaging_type": "DISPERSIVE"})


def quick(**over):
    opt = cli._quick_options()
    opt.ref_frac_unc = 0.03
    for k, v in over.items():
        setattr(opt, k, v)
    return opt


def silent(*a, **k):
    pass


@pytest.fixture(scope="module")
def clean_result():
    return cli.analyze_run(make_run(seed=1), quick(), log=silent)


def test_clean_scanned_run_recovers_truth_and_passes(clean_result):
    R = clean_result
    f, s = R["result"]["f_rabi_hz"], R["result"]["sigma_stat_hz"]
    assert abs(f - F_TRUE) < 3 * s, (f, s)
    assert s < 0.01 * F_TRUE
    g = R["gates"]
    for name in ("timing", "apd_signal", "polarity", "joint_localized", "joint_no_railing",
                 "joint_adequacy", "block_consistency", "reference_agreement", "rp_gof",
                 "turn_on_delay"):
        assert g[name]["status"] == cli.PASS, (name, g[name])
    assert R["verdicts"]["t_pi"]["status"] == cli.PASS, R["verdicts"]
    assert "kexp/config/expt_params.py" in R["proposal"]
    # nuisances recovered within 3 sigma
    J = R["joint"]["axes"]
    assert abs(J["frequency_lightshift"]["mean"] - LS) < 3 * J["frequency_lightshift"]["std"]
    assert abs(J["back_action_coherence"]["mean"] - COH) < 3 * J["back_action_coherence"]["std"]


def test_design_and_timing_are_reported(clean_result):
    assert clean_result["design"]["kind"].startswith("scanned")
    assert clean_result["design"]["n_distinct_schedules"] == FRACS.size
    assert abs(clean_result["timing"]["period_minus_pulse_us"] - OVERHEAD * 1e6) < 1e-3


def test_stale_apd_calibration_fails_fixed_cal_not_joint():
    # endpoints 15 mV off and an understated sigma: the run-76245 failure class
    stale = true_cal(v_apd_all_down=V_DOWN + 0.015, v_apd_all_up=V_DOWN + V_RANGE + 0.015,
                     std_n_photons_per_shot=100.0)
    R = cli.analyze_run(make_run(seed=2, n_rep=10, cal=stale), quick(skip_pinned=True),
                        log=silent)
    assert R["gates"]["rp_gof"]["status"] == cli.FAIL
    assert R["verdicts"]["fixed_cal"]["status"] == cli.FAIL
    f, s = R["result"]["f_rabi_hz"], R["result"]["sigma_stat_hz"]
    assert abs(f - F_TRUE) < 3 * s
    assert "rp_gof" not in R["verdicts"]["t_pi"]["failed"]


def test_stale_bloch_constants_pass_gof_but_fail_rp_vs_joint():
    # coherence 0.80 / light shift 30 kHz stored, truth 0.62 / 40.6 kHz: the fixed-
    # calibration fit still looks fine by GOF and is biased -- the silent failure
    # the RabiPosterior-vs-joint gate exists for.
    stale = true_cal(back_action_coherence=0.8, frequency_lightshift=30e3)
    R = cli.analyze_run(make_run(seed=11, n_rep=10, cal=stale), quick(skip_pinned=True),
                        log=silent)
    assert R["gates"]["rp_gof"]["status"] == cli.PASS
    assert R["gates"]["rp_vs_joint"]["status"] == cli.FAIL
    assert R["verdicts"]["fixed_cal"]["status"] == cli.FAIL


def test_inverted_readout_fails_polarity():
    R = cli.analyze_run(make_run(seed=3, invert=True), quick(), log=silent)
    assert R["gates"]["polarity"]["status"] == cli.FAIL
    assert R["verdicts"]["t_pi"]["status"] == cli.FAIL
    assert not R["proposal"]


def test_drift_inside_run_fails_block_check():
    R = cli.analyze_run(make_run(seed=4, n_rep=6, drift_frac=0.04), quick(), log=silent)
    assert R["gates"]["block_consistency"]["status"] == cli.FAIL, R["blocks"]
    assert R["verdicts"]["t_pi"]["status"] == cli.FAIL


def test_wrong_turn_on_delay_is_found_by_the_profile():
    # data made with a 0.8 us dead time, analysed with the params' 127 ns
    opt = quick(skip_pinned=True, delay_profile_ns=(0., 127., 300., 500., 650., 800., 950.),
                delay_profile_f_n=601)
    R = cli.analyze_run(make_run(seed=8, n_rep=10, t0_true=800e-9), opt, log=silent)
    DP = R["delay_profile"]
    assert R["gates"]["turn_on_delay"]["status"] == cli.FAIL, DP
    assert abs(DP["t0_hat_ns"] - 800.0) < max(3 * DP["t0_sigma_ns"], 60.0), DP
    assert R["verdicts"]["t_pi"]["status"] == cli.FAIL


def test_no_light_on_apd_fails_signal_gate():
    R = cli.analyze_run(make_run(seed=5, no_light=True), quick(skip_pinned=True), log=silent)
    assert R["gates"]["apd_signal"]["status"] == cli.FAIL
    assert R["verdicts"]["t_pi"]["status"] == cli.FAIL


def test_exclusions_are_counted_with_reasons():
    rd0 = make_run(seed=6)
    apd = rd0.apd.copy()
    apd[3, 2] = np.nan
    completed = np.ones(apd.shape[0], dtype=bool)
    completed[[7, 8]] = False
    rd = cli.run_data_from_arrays(1, apd, rd0.t_eff, true_cal(), completed=completed,
                                  acq_order=rd0.acq_order)
    assert rd.n_shot == apd.shape[0] - 3
    reasons = {e["reason"]: e["rows"] for e in rd.excluded}
    assert reasons["never taken (run incomplete)"] == [7, 8]
    assert reasons["non-finite APD value"] == [3]
    assert sorted(rd.acq_order.tolist()) == list(range(rd.n_shot))


def test_zoom_window_refuses_unlocalized_posterior():
    assert cli._zoom_window(80e3, 20e3, (40e3, 150e3), (10e3, 200e3), 250.0) is None
    lo, hi, n = cli._zoom_window(76e3, 200.0, (75.6e3, 76.4e3), (10e3, 200e3), 250.0)
    assert lo < 75.6e3 and hi > 76.4e3 and (hi - lo) / (n - 1) <= 250.0


def test_count_modes():
    x = np.linspace(0, 1, 201)
    one = np.exp(-0.5 * ((x - 0.5) / 0.05) ** 2)
    two = one + np.exp(-0.5 * ((x - 0.8) / 0.03) ** 2)
    assert cli._count_modes(one / one.sum()) == 1
    assert cli._count_modes(two / two.sum()) == 2


def test_out_dir_allow_list(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(cli, "OUTPUT_ROOT", root)
    assert cli._check_out_dir(Path("sub")) == (root / "sub").resolve()
    assert cli._check_out_dir(root) == root.resolve()
    for bad in (tmp_path / "elsewhere", root / ".." / "elsewhere", Path("..") / "escape"):
        with pytest.raises(SystemExit):
            cli._check_out_dir(bad)


def _fake_ad(rd, run_id):
    """What load_run reads off an atomdata, built from a synthetic RunData."""
    c = rd.cal
    p = SimpleNamespace(
        t_img_pulse=c.t_img_pulse, frequency_lightshift=c.frequency_lightshift,
        back_action_coherence=c.back_action_coherence,
        feedback_measurement_midpoint_fraction=c.feedback_measurement_midpoint_fraction,
        feedback_measurement_midpoint_remap_enabled=True,
        v_apd_all_up=c.v_apd_all_up, v_apd_all_down=c.v_apd_all_down,
        n_photons_per_shot=c.n_photons_per_shot, std_n_photons_per_shot=c.std_n_photons_per_shot,
        t_raman_pi_pulse=c.t_raman_pi_pulse, t_raman_turn_on_delay=c.t_turn_on_delay,
        N_pulses=rd.n_pulse, N_repeats=4, amp_imaging=0.2)
    data = SimpleNamespace(apd=rd.apd, t_raman_pulse=rd.t_eff, t=rd.t_rec,
                           apd_reference=rd.apd_reference)
    ri = SimpleNamespace(run_id=run_id, imaging_type=1, expt_class=b"apd_joint_calibration",
                         run_datetime_str=b"synthetic", data_complete=True,
                         shot_order=rd.acq_order)
    return SimpleNamespace(p=p, data=data, run_info=ri, xvarnames=["t_raman_pulse"])


def test_main_end_to_end_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path)            # allow-list root -> the temp dir
    rd = make_run(seed=7)
    loader = lambda rid: _fake_ad(rd, rid)                      # noqa: E731
    doc = cli.main(["424242", "--quick", "--no-figures", "--out", str(tmp_path),
                    "--cal", "back_action_coherence=0.62"], loader=loader)
    out = json.loads((tmp_path / "results.json").read_text())
    assert out["runs"][0]["run_id"] == 424242
    assert out["runs"][0]["calibration_sources"]["back_action_coherence"] == "override"
    assert out["runs"][0]["acq_order_source"] == "run_info.shot_order"
    assert set(out["runs"][0]["verdicts"]) == {"t_pi", "nuisances", "fixed_cal"}
    assert out["gates"]["GATE_GOF_LIMIT"] == cli.GATE_GOF_LIMIT
    assert doc["combined"] is None


def test_main_rejects_relative_run_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["0", "--out", str(tmp_path)], loader=lambda rid: None)
