"""liveOD picks the absorption cross section per shot from the field at imaging,
by the analysis's own rule. The analysed images and the experiment's report of
the shot arrive separately and in either order."""
import math
import types

import numpy as np
import pytest

from waxa.calibrations import cross_section as policy
from kexp.util.live_od.shot_cross_section import (ShotCrossSectionPairing,
                                                  cross_section_for_shot)

OD_AREA = 1.0e-9        # m^2: integrated OD x pixel area, before division
HIGH, LOW = {policy.I_OUTER_KEY: 180.0}, {policy.I_OUTER_KEY: 0.0}


def analysed(od_area=OD_AREA):
    return {'shot_idx': 0, 'xvar_values': {'stale': 1.0}, 'atom_number': od_area,
            'atom_number_fit_area_x': 2 * od_area, 'atom_number_fit_area_y': float('nan')}


def test_rule_is_the_analysis_rule():
    assert cross_section_for_shot(HIGH) == (policy.SIGMA_HF_M2, policy.TAG_HF)
    assert cross_section_for_shot(LOW) == (policy.SIGMA_LF_M2, policy.TAG_LF)
    for nothing in (None, {}, {'some_other_key': 3.0}):
        assert cross_section_for_shot(nothing) == (policy.SIGMA_FALLBACK_M2, policy.TAG_FALLBACK)


def test_images_first_then_the_report():
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    assert pairing.add_analysis(0, analysed(), calibrated=True) == []       # waits
    (done,) = pairing.add_conditions(0, HIGH, {'t_tof': 5e-3})
    assert done['atom_number'] == pytest.approx(OD_AREA / policy.SIGMA_HF_M2)
    assert done['atom_number_fit_area_x'] == pytest.approx(2 * OD_AREA / policy.SIGMA_HF_M2)
    assert math.isnan(done['atom_number_fit_area_y'])
    assert done['atom_cross_section_m2'] == policy.SIGMA_HF_M2
    assert done['atom_cross_section_source'] == policy.TAG_HF
    assert done['xvar_values'] == {'t_tof': 5e-3}           # this shot's, not the stale ones


def test_report_first_then_the_images():
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    assert pairing.add_conditions(0, LOW, {'x': 1.0}) == []
    (done,) = pairing.add_analysis(0, analysed(), calibrated=True)
    assert done['atom_number'] == pytest.approx(OD_AREA / policy.SIGMA_LF_M2)
    assert done['atom_cross_section_source'] == policy.TAG_LF


def test_high_and_low_field_shots_in_one_run():
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    out = []
    for idx, conditions in enumerate([HIGH, LOW, HIGH]):
        out += pairing.add_analysis(idx, analysed(), calibrated=True)
        out += pairing.add_conditions(idx, conditions)
    assert [d['atom_cross_section_source'] for d in out] == [policy.TAG_HF, policy.TAG_LF, policy.TAG_HF]
    assert out[0]['atom_number'] / out[1]['atom_number'] == pytest.approx(2 * math.pi / 3, rel=1e-4)


def test_a_shot_never_reported_is_emitted_with_the_fallback():
    """An experiment process from before shot_conditions existed."""
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    assert pairing.add_analysis(0, analysed(), calibrated=True) == []
    (old,) = pairing.add_analysis(1, analysed(), calibrated=True)       # shot 0 gives up waiting
    assert old['atom_cross_section_source'] == policy.TAG_FALLBACK
    assert old['atom_number'] == pytest.approx(OD_AREA / policy.SIGMA_FALLBACK_M2)


def test_an_empty_report_uses_the_fallback_at_once():
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    pairing.add_analysis(0, analysed(), calibrated=True)
    (done,) = pairing.add_conditions(0, {})
    assert done['atom_cross_section_source'] == policy.TAG_FALLBACK


def test_without_pixel_calibration_nothing_is_divided():
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    pairing.add_analysis(0, analysed(od_area=1234.5), calibrated=False)
    (done,) = pairing.add_conditions(0, HIGH)
    assert done['atom_number'] == 1234.5
    assert done['atom_cross_section_source'] == 'uncalibrated-integrated-od'


def test_reports_without_images_do_not_pile_up():
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    for idx in range(1000):
        assert pairing.add_conditions(idx, HIGH) == []
    assert len(pairing._conditions) <= 1


def test_without_a_rule_nothing_is_divided():
    """waxx's default: a lab that configures no rule gets integrated OD, not
    potassium's numbers."""
    pairing = ShotCrossSectionPairing()
    pairing.add_analysis(0, analysed(od_area=7.0), calibrated=True)
    (done,) = pairing.add_conditions(0, HIGH)
    assert done['atom_number'] == 7.0
    assert done['atom_cross_section_source'] == 'no-cross-section-rule'


def test_reset_starts_a_new_run():
    pairing = ShotCrossSectionPairing(cross_section_for_shot)
    pairing.add_analysis(0, analysed(), calibrated=True)
    pairing.reset()
    assert pairing.add_conditions(0, HIGH) == []


# ---------------- the experiment side ----------------

def test_shot_conditions_are_the_single_valued_containers():
    from waxx.base.expt import Expt
    data = types.SimpleNamespace(
        keys=['i_outer_imaging', 'apd', 'trace', 'label'],
        i_outer_imaging=types.SimpleNamespace(shot_data=np.array([181.5])),
        apd=types.SimpleNamespace(shot_data=np.array([7], dtype=np.int32)),
        trace=types.SimpleNamespace(shot_data=np.zeros(8)),
        label=types.SimpleNamespace(shot_data=np.array(['x'])))
    expt = types.SimpleNamespace(data=data)
    assert Expt._shot_conditions(expt) == {'i_outer_imaging': 181.5, 'apd': 7.0}


def test_shot_conditions_never_raise():
    from waxx.base.expt import Expt
    assert Expt._shot_conditions(types.SimpleNamespace(data=None)) == {}


def test_client_sends_the_conditions_and_old_callers_still_work():
    from kexp.util.live_od import live_od_client as lc
    sent = []
    client = lc.LiveODClient.__new__(lc.LiveODClient)
    client.last_reset_requested = False
    client._send_recv = lambda payload, rcvtimeo_ms=None: (sent.append(payload)
                                                          or {"ok": True, "reset_requested": False})
    client.shot_complete(0, 2, {'x': 1.0}, shot_conditions=HIGH)
    client.shot_complete(1, 2, {'x': 2.0})
    assert sent[0]["shot_conditions"] == HIGH and sent[1]["shot_conditions"] == {}


# ---------------- the real Analyzer, offline ----------------

def test_analyzer_emits_atom_numbers_once_the_shot_is_reported(monkeypatch):
    pytest.importorskip("PyQt6")
    from queue import Queue
    from kexp.util.live_od.gui.analyzer import Analyzer
    from waxx.util.live_od import config as live_od_config

    # the rule reaches the Analyzer through the active config, as in the launcher
    monkeypatch.setattr(live_od_config, "_active",
                        live_od_config.LiveODConfig(cross_section_for_shot=cross_section_for_shot))
    analyzer = Analyzer(Queue())
    analyzer.set_server(types.SimpleNamespace(get_requested_metrics=lambda: {'atom_number'}))
    analyzer.set_camera_params({'pixel_size_m': 4.0e-6, 'magnification': 2.0})
    emitted = []
    analyzer.shot_scalars_signal.connect(emitted.append)

    od = np.full((10, 10), 0.5)
    dx = 4.0e-6 / 2.0
    expected_od_area = od.sum() * dx * dx

    analyzer._emit_scalars(od, od.sum(axis=0), od.sum(axis=1))
    assert emitted == []                                # waits for the experiment's report
    analyzer.set_xvar_values({'t_tof': 5e-3})
    analyzer.set_shot_conditions(0, HIGH)
    (scalars,) = emitted
    assert scalars['atom_number'] == pytest.approx(expected_od_area / policy.SIGMA_HF_M2)
    assert scalars['atom_cross_section_source'] == policy.TAG_HF
    assert scalars['xvar_values'] == {'t_tof': 5e-3}

    analyzer.reset()
    analyzer.set_shot_conditions(0, LOW)                # report first this time
    analyzer._emit_scalars(od, od.sum(axis=0), od.sum(axis=1))
    assert emitted[-1]['atom_number'] == pytest.approx(expected_od_area / policy.SIGMA_LF_M2)


# ---------------- the SHOT_COMPLETE handler, through a stand-in object ----------------

def _recording_signal(log, name):
    return types.SimpleNamespace(emit=lambda *args: log.append((name, args)))


def handler_stand_in(log):
    import threading
    return types.SimpleNamespace(
        _shot_timestamps=[], _init_run_time=0.0, _shot_durations=[], _reset_requested=False,
        _adjust_lock=threading.Lock(), _adjust_values={},
        shot_progress_signal=_recording_signal(log, 'progress'),
        shot_conditions_signal=_recording_signal(log, 'conditions'),
        shot_timing_signal=_recording_signal(log, 'timing'),
        shot_adjust_values_signal=_recording_signal(log, 'adjust'))


def test_handler_passes_the_conditions_on_after_the_xvars():
    from kexp.util.live_od.live_od_server import LiveODServer
    log = []
    reply = LiveODServer._handle_shot_complete(
        handler_stand_in(log),
        {"shot_idx": 3, "N_shots_total": 9, "xvar_values": {'x': 1.0}, "shot_conditions": HIGH})
    assert reply["ok"] and reply["reset_requested"] is False
    names = [name for name, _ in log]
    assert names.index('progress') < names.index('conditions')      # xvars reach the Analyzer first
    assert dict(log)['conditions'] == (3, HIGH)


def test_handler_tolerates_an_experiment_that_sends_no_conditions():
    from kexp.util.live_od.live_od_server import LiveODServer
    log = []
    LiveODServer._handle_shot_complete(handler_stand_in(log),
                                       {"shot_idx": 0, "N_shots_total": 1, "xvar_values": {}})
    assert dict(log)['conditions'] == (0, {})
