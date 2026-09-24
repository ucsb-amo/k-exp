"""kexp.config.live_od: kexp's values for the waxx LiveODConfig.

The saver is stubbed: only an experiment working through liveOD may construct
the real one (lab-rules.md section 1). Camera keys are taken from the module so
this file names no hardware.
"""
import subprocess
import sys

import pytest


def test_importing_the_module_has_no_side_effects():
    # loaded by path: importing it as kexp.config.live_od would import kexp itself
    code = ("import sys, importlib.util as u; "
            "spec = u.find_spec('kexp'); root = list(spec.submodule_search_locations)[0]; "
            "s = u.spec_from_file_location('cfg_builder', root + '/config/live_od.py'); "
            "m = u.module_from_spec(s); s.loader.exec_module(m); "
            "sys.exit(1 if 'kexp' in sys.modules else 0)")
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


@pytest.fixture
def cfg_and_module(monkeypatch):
    import waxa.data

    class StubSaver:
        def __init__(self, *args, **kwargs):
            pass
    monkeypatch.setattr(waxa.data, "DataSaver", StubSaver)
    from kexp.config import live_od
    return live_od.make_live_od_config(), live_od


def test_camera_bar_matches_the_declared_order(cfg_and_module):
    cfg, module = cfg_and_module
    assert [p.key for p in cfg.camera_params_list] == list(module.CAMERA_BAR_KEYS)
    assert cfg.cameras_open_on_start == []          # every camera starts closed, as before


def test_every_camera_key_resolves_to_its_own_params(cfg_and_module):
    cfg, _ = cfg_and_module
    for params in cfg.camera_params_list:
        assert cfg.resolve_camera_params(params.key) is params
    assert cfg.resolve_camera_params("no_such_key") is None


def test_identity_is_unchanged(cfg_and_module):
    """A new app id un-groups the pinned taskbar button."""
    cfg, _ = cfg_and_module
    assert cfg.app_user_model_id == "weldlab.kexp.gui.live_od"
    assert cfg.window_title == "LiveOD Server"


def test_cross_section_rule_is_the_analysis_rule(cfg_and_module):
    cfg, _ = cfg_and_module
    from waxa.calibrations import cross_section as policy
    assert cfg.cross_section_for_shot({policy.I_OUTER_KEY: 180.0}) == (policy.SIGMA_HF_M2, policy.TAG_HF)
    assert cfg.cross_section_for_shot({policy.I_OUTER_KEY: 0.0}) == (policy.SIGMA_LF_M2, policy.TAG_LF)
    assert cfg.cross_section_for_shot(None) == (policy.SIGMA_FALLBACK_M2, policy.TAG_FALLBACK)


def test_params_namespace_has_the_image_counts(cfg_and_module):
    cfg, _ = cfg_and_module
    assert hasattr(cfg.params_factory(), "N_img")
