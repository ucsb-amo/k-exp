"""kexp.analysis.apd_state_mapping on synthetic runs (no data files read; outputs only to pytest's tmp_path)."""

import json
import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pytest

import kexp.analysis.apd_state_mapping as asm

T_PI, T_DEAD, P = 6.5e-6, 0.3e-6, 5
V_UP, V_DOWN = -0.170, -0.208
CURRENT = dict(t_img_pulse=5e-6, amp_imaging=0.2, v_apd_all_up=-0.12361, v_apd_all_down=-0.19702,
               n_photons_per_shot=1336.2, std_n_photons_per_shot=212.75,
               feedback_measurement_midpoint_fraction=0.4719)


def _fake_run(seed, v_up=V_UP):
    rng = np.random.default_rng(seed)
    t = np.repeat(T_PI * np.linspace(0, 2, 21), 2)
    rng.shuffle(t)
    s = np.cos(np.pi / (T_PI - T_DEAD) * np.clip(t - T_DEAD, 0, None))
    apd = (V_DOWN + (v_up - V_DOWN) * 0.5 * (1 + s))[:, None] + rng.normal(0, 7e-3, (t.size, P))
    params = {"t_raman_pi_pulse": T_PI, "t_raman_pulse_offset": 127e-9, "amp_imaging": 0.2, "t_pci_pulse": 5e-6,
              "N_pulses": P, "t_between_pulses_mu": 25000, "phase_slm_mask": 2.028 * np.pi}
    info = dict(run_id=seed, datetime="2026-09-27_11-00-00", experiment="sigma_z",
                timestamps=5.5 * np.arange(t.size) + 300.0 * seed, params=params, data_complete=None)
    return dict(t=t, apd=apd, info=info), SimpleNamespace(**params), None


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(asm, "load_run", lambda rid, with_scope=True, scope_windows=None: _fake_run(int(rid)))
    monkeypatch.setattr(asm, "current_feedback_params",
                        lambda: (dict(CURRENT), {"v_apd_all_up_opx": -0.12361, "v_apd_all_down_opx": -0.19702}))


def test_proposal_block_follows_the_lab_convention(fake):
    m = asm.apd_state_mapping([1, 2, 3], n_boot=50, date="2026-09-27")
    assert m.cal.ok, m.cal.reason
    vals = m.proposed_values()
    assert set(vals) == {"v_apd_all_up", "v_apd_all_down", "feedback_measurement_midpoint_fraction",
                         "std_n_photons_per_shot"}                   # no scope -> N is kept
    p = m.cal.proposal
    assert abs(vals["v_apd_all_up"][1] - V_UP) < 4 * p["v_up_err"]
    assert vals["std_n_photons_per_shot"][1] == pytest.approx(CURRENT["n_photons_per_shot"] * p["sigma_fraction"])
    block = m.params_block()
    assert "# self.v_apd_all_up = -0.12361" in block
    assert "#1-3, 2026-09-27" in block
    assert "n_photons_per_shot kept" in block
    assert m.cal.pulses_used == (0, 1, 2, 3, 4)                     # every pulse by default
    json.dumps(m.to_dict(), default=str)


def test_skip_first_pulse_and_param_consistency(fake, monkeypatch):
    m = asm.apd_state_mapping([4, 5], skip_first_pulse=True, n_boot=0)
    assert m.cal.pulses_used == (1, 2, 3, 4)
    real = asm.load_run

    def differing(rid, with_scope=True, scope_windows=None):
        d, prm, sc = real(rid)
        d["info"]["params"] = dict(d["info"]["params"], amp_imaging=0.2 + 0.1 * (int(rid) == 7))
        return d, prm, sc
    monkeypatch.setattr(asm, "load_run", differing)
    m2 = asm.apd_state_mapping([6, 7], n_boot=0)
    assert any("amp_imaging differs" in w for w in m2.param_warnings)


def test_cli_writes_only_to_out(fake, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(asm, "OUTPUT_ROOT", str(tmp_path))     # allow-list root -> the temp dir
    rc = asm.main(["1", "2", "3", "--out", str(tmp_path), "--bootstrap", "20", "--date", "2026-09-27"])
    assert rc == 0
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["apd_state_mapping_1-3.json", "apd_state_mapping_1-3_pulses.png",
                     "apd_state_mapping_1-3_summary.png"]
    d = json.loads((tmp_path / "apd_state_mapping_1-3.json").read_text(encoding="utf-8"))
    assert d["run_ids"] == [1, 2, 3] and "v_apd_all_up" in d["proposed"]
    assert "proposed (review before applying)" in capsys.readouterr().out


def test_out_dir_allow_list(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(asm, "OUTPUT_ROOT", str(root))
    assert asm._check_out_dir("sub") == os.path.realpath(str(root / "sub"))
    assert asm._check_out_dir(str(root)) == os.path.realpath(str(root))
    for bad in (str(tmp_path / "elsewhere"), str(root / ".." / "elsewhere"), "..\\escape"):
        with pytest.raises(SystemExit):
            asm._check_out_dir(bad)
