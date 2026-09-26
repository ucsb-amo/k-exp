"""Offline tests for the K-machine OPX wiring (kexp.control.opx.opx_config)
and the component layer (kexp.control.opx.components): the handoff
contract against the REAL ExptParams, the config-time parameter guard, the
component-generated config against a golden snapshot of the hand-written
config it replaced, and the JSON provenance.

Run from the workspace root with the root venv:
    .venv/Scripts/python.exe -m pytest k-exp/tests/test_opx_config.py -q -p no:cacheprovider

Nothing here opens a socket or imports qm at module level.
"""

import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

from waxa.base.xvar import xvar

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opx_sim_fixture import fake_raman_expt, fake_config, config_pulse  # noqa: E402

from kexp.control.opx.units import hz_to_int, s_to_ns, s_to_cc, MAX_ANALOG_V  # noqa: E402
from kexp.control.opx.params_bridge import build_shot_tables  # noqa: E402
from kexp.control.opx.channels import ChannelMap, ChannelSpec  # noqa: E402
from kexp.control.opx.components import (Machine, Sticky, DigitalLine,  # noqa: E402
                                         AnalogDrive, IntegratedInput,
                                         qm_qua_version)
from kexp.control.opx.opx_config import (kexp_channel_map, build_opx_config,  # noqa: E402
                                         build_machine, config_time_params,
                                         CONFIG_TIME_PARAMS,
                                         HANDBACK_HOLD_PARAMS,
                                         RAMAN_TRANSITION_PARAM,
                                         RAMAN_POWER_FRACTION_PARAM)


# ---------------------------------------------------------------------------
# a prepared experiment with the REAL kexp ExptParams
# ---------------------------------------------------------------------------

class RealParamsExpt:
    """Duck-types what kexp_channel_map / build_opx_config / build_shot_tables
    need of a waxx Expt after finish_prepare -- with a real
    kexp.config.expt_params.ExptParams (no fabricated params, so a parameter
    the map reads that ExptParams no longer defines fails here) and the
    fixture's real RamanBeamPair for the drive split.

    xvars: [(key, values), ...]; values[0] is plugged into params, as
    finish_prepare's plug_in_xvars does before the OPX map is built.
    """

    def __init__(self, xvars=()):
        from kexp.config.expt_params import ExptParams
        self.params = ExptParams()
        self.p = self.params
        r = fake_raman_expt()
        self.dds, self.raman = r.dds, r.raman
        self.scan_xvars = [xvar(k, np.asarray(v, dtype=float), position=i)
                           for i, (k, v) in enumerate(xvars)]
        self.xvardims = [len(xv.values) for xv in self.scan_xvars]
        self.xvarnames = [xv.key for xv in self.scan_xvars]
        for xv in self.scan_xvars:
            vars(self.params)[xv.key] = xv.values[0]

    def compute_new_derived(self):
        pass


def _stub():
    """The config stub test_opx used for the hand-written config: fixture
    dds defaults (0.337 / 0.324 V, 80 / 150 MHz centers), transition
    119.4639 MHz, 5 us acquire, 5 us integration window from 0."""
    ex = fake_raman_expt(a_80=0.337, a_150=0.324,
                         frequency_raman_transition=119.4639e6)
    p = ex.params
    p.t_imaging_pulse_apd_abs = 5.e-6
    p.t_opx_integration_start = 0.
    p.t_opx_integration_len = 5.e-6
    p.t_opx_handoff_artiq_side = 350.e-9
    p.t_opx_handoff_opx_side = 1.e-6
    p.t_opx_handback_artiq_trigger_receive_latency = 1.e-6
    p.t_opx_handback_artiq_rtio_delay = 2.e-6
    p.t_opx_handback_switch_fall_delay = 2.e-6
    return ex


# ---------------------------------------------------------------------------
# D1: the handoff contract, against the real ExptParams
# ---------------------------------------------------------------------------

def test_kexp_channel_map_from_real_expt_params():
    ex = RealParamsExpt()
    p = ex.params
    for key in CONFIG_TIME_PARAMS + (RAMAN_TRANSITION_PARAM,):
        assert hasattr(p, key), f"ExptParams no longer defines {key!r}"

    cmap = kexp_channel_map(ex)
    # settle = the ARTIQ-side sum: RF on at artiq_side, settled (and the
    # kernel back in the caller) at artiq_side + opx_side
    assert cmap.t_handoff_settle_s == (p.t_opx_handoff_artiq_side
                                       + p.t_opx_handoff_opx_side)
    # hold = the hand-back sum: the edge reaches ARTIQ, ARTIQ takes its RF
    # back rtio_delay after its timestamp, the switches fall
    assert HANDBACK_HOLD_PARAMS == (
        't_opx_handback_artiq_trigger_receive_latency',
        't_opx_handback_artiq_rtio_delay',
        't_opx_handback_switch_fall_delay')
    assert cmap.t_handback_hold_s == (
        p.t_opx_handback_artiq_trigger_receive_latency
        + p.t_opx_handback_artiq_rtio_delay
        + p.t_opx_handback_switch_fall_delay)
    assert cmap.machine.extra['t_handback_hold_s'] == cmap.t_handback_hold_s
    for key in HANDBACK_HOLD_PARAMS:
        assert cmap.machine.extra[key] == getattr(p, key)
    assert cmap.guarded_channels == ('raman', 'imaging')
    assert cmap.sync_channel == 'raman'
    assert cmap.spec('imaging').t_acquire_s == p.t_imaging_pulse_apd_abs
    assert cmap.spec('imaging').t_integration_s == p.t_opx_integration_len
    assert cmap.spec('raman').transition_param == RAMAN_TRANSITION_PARAM
    # the new fields A2's manager codes against
    assert cmap.config_time_params == CONFIG_TIME_PARAMS
    assert isinstance(cmap.machine, Machine)
    assert cmap.machine.extra['t_handoff_settle_s'] == cmap.t_handoff_settle_s

    cfg = build_opx_config(ex)
    assert config_pulse(cfg, 'apd', 'acquire')['length'] == \
        s_to_ns(p.t_imaging_pulse_apd_abs)
    f150, f80 = ex.raman.ao_frequencies(p.frequency_raman_transition)
    assert cfg['elements']['raman_80']['intermediate_frequency'] == hz_to_int(f80)
    assert cfg['elements']['raman_150']['intermediate_frequency'] == hz_to_int(f150)
    assert cfg['waveforms']['raman_80.cw.wf']['sample'] == ex.dds.raman_80_plus.amplitude


def test_settle_wait_is_the_sum_on_the_program_side():
    # the builder waits ChannelMap.t_handoff_settle_s after the block plays;
    # with the real numbers that is 1.35 us -> 337.5 cc, rounded to the grid
    from qm import generate_qua_script
    from kexp.control.opx.builder import OPXProgramBuilder
    from kexp.control.opx.sequence import OPXSequence

    ex = RealParamsExpt([('t_raman_pulse', [0., 4.e-6])])
    tables = build_shot_tables(ex)
    cmap = kexp_channel_map(ex, tables)
    cfg = build_opx_config(ex, tables)

    def body(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)
    seq = OPXSequence(body, name='_cfg_rabi', claims=('raman',))
    prog, _ctx = OPXProgramBuilder(seq, cmap, tables, tables.n_shots).trace()
    src = generate_qua_script(prog)
    settle_cc = s_to_cc(cmap.t_handoff_settle_s)
    assert settle_cc in (337, 338)
    i_trigger = src.index("wait_for_trigger('raman_switch')")
    i_block = src.index("play('block', 'raman_switch'", i_trigger)   # + timestamp_stream
    i_settle = src.index(f"wait({settle_cc}, 'raman_switch'", i_block)
    i_expose = src.index("play('pass', 'raman_switch', duration=", i_settle)
    assert i_trigger < i_block < i_settle < i_expose
    # the program text names elements and ops only -- never a derived
    # pulse/waveform/weight name, and none of the retired hand-written ones
    for name in list(cfg['pulses']) + list(cfg['waveforms']) + \
            list(cfg['digital_waveforms']) + list(cfg['integration_weights']):
        assert name not in src
    for old in ('block_pulse', 'pass_pulse', 'apd_acquire', 'raman_80_cw'):
        assert old not in src
    # and with the config attached it still serializes
    assert 'raman_switch' in generate_qua_script(prog, cfg)


def test_handback_hold_is_the_sum_on_the_program_side():
    # from the hand-back trigger the program waits ChannelMap.t_handback_hold_s
    # on both RF-block switches AND both analog drives before it releases
    # the blocks, and the epilogue ramp_to_zero comes after that wait --
    # never at the trigger, while ARTIQ still routes the AOs to the OPX
    from qm import generate_qua_script
    from kexp.control.opx.builder import OPXProgramBuilder
    from kexp.control.opx.sequence import OPXSequence

    ex = RealParamsExpt([('t_raman_pulse', [0., 4.e-6])])
    p = ex.params
    tables = build_shot_tables(ex)
    cmap = kexp_channel_map(ex, tables)

    def body(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)
    seq = OPXSequence(body, name='_cfg_hold', claims=('raman',))
    prog, _ctx = OPXProgramBuilder(seq, cmap, tables, tables.n_shots).trace()
    src = generate_qua_script(prog)
    hold_cc = s_to_cc(p.t_opx_handback_artiq_trigger_receive_latency
                      + p.t_opx_handback_artiq_rtio_delay
                      + p.t_opx_handback_switch_fall_delay)
    assert hold_cc == s_to_cc(cmap.t_handback_hold_s)
    i_trig = src.index("play('trigger', 'artiq_handback')")
    i_hold = src.index(f"wait({hold_cc}, 'raman_switch', 'imaging_switch', "
                       f"'raman_80', 'raman_150')", i_trig)
    i_rel = src.index("play('pass', 'raman_switch')", i_hold)
    i_rel2 = src.index("play('pass', 'imaging_switch')", i_rel)
    i_ramp = src.index("ramp_to_zero('raman_80'", i_rel2)
    assert i_trig < i_hold < i_rel < i_rel2 < i_ramp
    # nothing between the trigger and the hold wait
    between = src[i_trig:i_hold].splitlines()
    assert len(between) == 2, between


# ---------------------------------------------------------------------------
# D2: config-time parameters
# ---------------------------------------------------------------------------

def test_config_time_params_listed_and_accessed():
    ex = RealParamsExpt([('t_raman_pulse', [1.e-6, 2.e-6])])
    tables = build_shot_tables(ex)
    assert tables.accessed == set()
    cmap = kexp_channel_map(ex, tables)
    assert set(CONFIG_TIME_PARAMS) <= tables.accessed
    assert RAMAN_TRANSITION_PARAM in tables.accessed
    assert cmap.config_time_params == CONFIG_TIME_PARAMS
    assert config_time_params(ex) == CONFIG_TIME_PARAMS
    # the transition is deliberately NOT config-time: it has a shot-time
    # route (the builder re-points the drives per shot)
    assert RAMAN_TRANSITION_PARAM not in CONFIG_TIME_PARAMS
    # build_opx_config records them too (tables given)
    t2 = build_shot_tables(ex)
    build_opx_config(ex, t2)
    assert set(CONFIG_TIME_PARAMS) <= t2.accessed

    # ... which is what makes the Adjust-panel guard cover them
    from kexp.control.opx.manager import check_live_adjust_conflicts
    ex._adjust_specs = [SimpleNamespace(key='t_raman_pi_pulse')]   # unrelated
    check_live_adjust_conflicts(ex, tables)
    for key in CONFIG_TIME_PARAMS:
        ex._adjust_specs = [SimpleNamespace(key=key)]
        with pytest.raises(RuntimeError, match=key):
            check_live_adjust_conflicts(ex, tables)


@pytest.mark.parametrize('key', CONFIG_TIME_PARAMS)
def test_scanned_config_time_param_is_refused(key):
    base = float(getattr(RealParamsExpt().params, key))
    ex = RealParamsExpt([(key, [base, base * 1.5 + 1.e-6])])
    tables = build_shot_tables(ex)
    with pytest.raises(RuntimeError, match='config-time'):
        build_opx_config(ex, tables)
    with pytest.raises(RuntimeError, match='config-time'):
        kexp_channel_map(ex, tables)
    with pytest.raises(RuntimeError, match=key):
        config_time_params(ex, tables)


def test_scanned_transition_is_not_refused():
    # scanning frequency_raman_transition is fine: the config is compiled at
    # the first EXECUTED shot and the builder re-points per shot
    f = 119.4639e6
    ex = RealParamsExpt([('frequency_raman_transition', [f + 1.e6, f])])
    tables = build_shot_tables(ex)
    cfg = build_opx_config(ex, tables)
    f150, f80 = ex.raman.ao_frequencies(f + 1.e6)
    assert cfg['elements']['raman_150']['intermediate_frequency'] == hz_to_int(f150)
    assert cfg['elements']['raman_80']['intermediate_frequency'] == hz_to_int(f80)
    m = kexp_channel_map(ex, tables).machine
    assert m.extra['frequency_raman_transition_hz'] == f + 1.e6
    assert 'shot tables' in m.extra['transition_source']
    # without tables the map reads the declared (plugged-in) value and
    # says so
    m0 = kexp_channel_map(ex).machine
    assert m0.extra['transition_source'] == 'params'


# ---------------------------------------------------------------------------
# Raman power fraction: the ARTIQ parameter, applied as amp() on the latch
# ---------------------------------------------------------------------------

def _trace_real(ex, claims=('raman',)):
    """Trace a one-op sequence against the real map -> (builder, tables,
    QUA source)."""
    from qm import generate_qua_script
    from kexp.control.opx.builder import OPXProgramBuilder
    from kexp.control.opx.sequence import OPXSequence

    def body(ctx):
        if 'raman' in claims:
            ctx.raman_pulse(ctx.p.t_raman_pi_pulse)
        else:
            ctx.wait_s(1.e-6)
    seq = OPXSequence(body, name='_cfg_fp_' + '_'.join(claims), claims=claims)
    tables = build_shot_tables(ex)
    b = OPXProgramBuilder(seq, kexp_channel_map(ex, tables), tables,
                          tables.n_shots)
    prog, _ctx = b.trace()
    return b, tables, generate_qua_script(prog)


def _latch_scales(src):
    """{element: amp() factor} of the analog latch plays in QUA source."""
    import re
    return {el: float(v) for el, v in re.findall(
        r"play\('cw', '(\w+)', amplitude_scale=([0-9.eE+-]+)\)", src)}


def test_raman_latch_is_sqrt_fraction_power_of_the_dds_default():
    # fraction_power_raman is the ARTIQ parameter: prep_raman ->
    # RamanBeamPair.set writes sqrt(f) x the dds default to each DDS. The
    # OPX config keeps the dds default (= fraction 1) and the latch plays it
    # at amp(sqrt(f)), so both sides drive the AOs at the same amplitude.
    ex = RealParamsExpt([('t_raman_pulse', [0., 4.e-6])])
    f = float(ex.params.fraction_power_raman)
    cmap = kexp_channel_map(ex)
    assert RAMAN_POWER_FRACTION_PARAM == 'fraction_power_raman'
    assert cmap.spec('raman').power_fraction_param == RAMAN_POWER_FRACTION_PARAM
    assert cmap.spec('imaging').power_fraction_param is None
    assert (cmap.machine.extra['raman_power_fraction_param']
            == RAMAN_POWER_FRACTION_PARAM)
    cfg = build_opx_config(ex)
    a80 = cfg['waveforms']['raman_80.cw.wf']['sample']
    a150 = cfg['waveforms']['raman_150.cw.wf']['sample']
    assert a80 == ex.dds.raman_80_plus.amplitude
    assert a150 == ex.dds.raman_150_plus.amplitude

    b, tables, src = _trace_real(ex)
    scales = _latch_scales(src)
    assert scales.keys() == {'raman_80', 'raman_150'}
    assert src.count("play('cw', ") == 2            # once per drive per run
    for s in scales.values():
        assert s == pytest.approx(np.sqrt(f), rel=1.e-12)
    # the same volts RamanBeamPair.set writes (dds0 = 150, dds1 = 80)
    assert a150 * scales['raman_150'] == pytest.approx(
        np.sqrt(f) * ex.raman._amplitude_0, rel=1.e-12)
    assert a80 * scales['raman_80'] == pytest.approx(
        np.sqrt(f) * ex.raman._amplitude_1, rel=1.e-12)
    for r in (r for r in b.log.records if r.macro == 'latch'):
        assert r.extra['power_fraction'] == f
        assert r.extra['amp_scale'] == pytest.approx(np.sqrt(f), rel=1.e-12)

    # read through ctx.p, so the Adjust panel refuses it
    from kexp.control.opx.manager import check_live_adjust_conflicts
    assert RAMAN_POWER_FRACTION_PARAM in tables.accessed
    ex._adjust_specs = [SimpleNamespace(key=RAMAN_POWER_FRACTION_PARAM)]
    with pytest.raises(RuntimeError, match=RAMAN_POWER_FRACTION_PARAM):
        check_live_adjust_conflicts(ex, tables)


def test_scanned_raman_power_fraction_refused_only_when_raman_claimed():
    from kexp.control.opx.manager import check_latch_param_xvars
    ex = RealParamsExpt([(RAMAN_POWER_FRACTION_PARAM, [0.3, 0.1])])
    cmap = kexp_channel_map(ex)
    with pytest.raises(RuntimeError, match=RAMAN_POWER_FRACTION_PARAM):
        check_latch_param_xvars(ex, cmap, ('raman',))
    with pytest.raises(RuntimeError, match='latch once per run'):
        _trace_real(ex)
    # a sequence that does not claim raman never latches the drives, so
    # ARTIQ may scan the fraction
    check_latch_param_xvars(ex, cmap, ('imaging',))
    _b, _t, src = _trace_real(ex, claims=('imaging',))
    assert "play('cw'" not in src


@pytest.mark.parametrize('f, match', [
    (-0.1, '>= 0'),
    (float('nan'), '>= 0'),
    (2.5, 'analog output limit'),        # 0.337 V x sqrt(2.5) = 0.53 V
    (4.0, r'amp\(\) range'),             # amp(2) is outside [-2, 2)
])
def test_bad_raman_power_fraction_is_refused(f, match):
    ex = RealParamsExpt()
    ex.params.fraction_power_raman = f
    with pytest.raises(ValueError, match=match):
        _trace_real(ex)


def test_power_fraction_one_latches_the_dds_default():
    ex = RealParamsExpt()
    ex.params.fraction_power_raman = 1.
    _b, _t, src = _trace_real(ex)
    assert _latch_scales(src) == {'raman_80': 1., 'raman_150': 1.}


# ---------------------------------------------------------------------------
# D3: component-generated config == the hand-written config it replaced
# ---------------------------------------------------------------------------

def _golden_hand_written(f_80, f_150, a_80=0.337, a_150=0.324,
                         acquire_ns=5000):
    """The config dict kexp.control.opx.opx_config.build_opx_config returned
    for _stub() before the component layer (branch jep/opx-integration,
    2026-09-24), verbatim -- element names, ops, sticky dicts, IFs, amps,
    windows. Only the pulse/waveform/marker/weight NAMES were allowed to
    change (to the QUAM rule)."""
    window = [(1.0, acquire_ns)]
    return {
        'controllers': {
            'con1': {
                'type': 'opx1',
                'analog_outputs': {1: {'offset': 0.0}, 2: {'offset': 0.0}},
                'digital_outputs': {1: {}, 2: {}, 3: {}, 4: {}},
                'analog_inputs': {1: {'offset': 0.0, 'gain_db': 0}},
            },
        },
        'elements': {
            'raman_80': {
                'singleInput': {'port': ('con1', 1)},
                'intermediate_frequency': f_80,
                'sticky': {'analog': True, 'duration': 100},
                'operations': {'cw': 'raman_80_cw'},
            },
            'raman_150': {
                'singleInput': {'port': ('con1', 2)},
                'intermediate_frequency': f_150,
                'sticky': {'analog': True, 'duration': 100},
                'operations': {'cw': 'raman_150_cw'},
            },
            'raman_switch': {
                'digitalInputs': {'in': {'port': ('con1', 1), 'delay': 0, 'buffer': 0}},
                'sticky': {'analog': True, 'digital': True, 'duration': 16},
                'operations': {'block': 'block_pulse', 'pass': 'pass_pulse'},
            },
            'imaging_switch': {
                'digitalInputs': {'in': {'port': ('con1', 2), 'delay': 0, 'buffer': 0}},
                'sticky': {'analog': True, 'digital': True, 'duration': 16},
                'operations': {'block': 'block_pulse', 'pass': 'pass_pulse'},
            },
            'artiq_handback': {
                'digitalInputs': {'in': {'port': ('con1', 3), 'delay': 0, 'buffer': 0}},
                'operations': {'trigger': 'handback_trigger_pulse'},
            },
            'apd': {
                'digitalInputs': {'in': {'port': ('con1', 4), 'delay': 0, 'buffer': 0}},
                'outputs': {'out1': ('con1', 1)},
                'time_of_flight': 200,
                'smearing': 0,
                'operations': {'acquire': 'apd_acquire'},
            },
        },
        'pulses': {
            'raman_80_cw': {'operation': 'control', 'length': 1000,
                            'waveforms': {'single': 'raman_80_wf'}},
            'raman_150_cw': {'operation': 'control', 'length': 1000,
                             'waveforms': {'single': 'raman_150_wf'}},
            'block_pulse': {'operation': 'control', 'length': 16,
                            'digital_marker': 'block_wf'},
            'pass_pulse': {'operation': 'control', 'length': 16,
                           'digital_marker': 'pass_wf'},
            'handback_trigger_pulse': {'operation': 'control', 'length': 200,
                                       'digital_marker': 'trigger_wf'},
            'apd_acquire': {'operation': 'measurement', 'length': acquire_ns,
                            'digital_marker': 'trigger_wf',
                            'integration_weights': {
                                'integration_window': 'integration_window',
                                'full_pulse': 'full_pulse'}},
        },
        'waveforms': {
            'raman_80_wf': {'type': 'constant', 'sample': a_80},
            'raman_150_wf': {'type': 'constant', 'sample': a_150},
        },
        'digital_waveforms': {
            'block_wf': {'samples': [(1, 0)]},
            'pass_wf': {'samples': [(0, 0)]},
            'trigger_wf': {'samples': [(1, 0)]},
        },
        'integration_weights': {
            'integration_window': {'cosine': window,
                                   'sine': [(0.0, ns) for _v, ns in window]},
            'full_pulse': {'cosine': [(1.0, acquire_ns)],
                           'sine': [(0.0, acquire_ns)]},
        },
    }


def _resolved(cfg):
    """The config with every name indirection followed: each element's
    operations map label -> the pulse's CONTENT (waveform samples, marker
    samples, weight arrays inlined), so two configs compare equal exactly
    when the machine would do the same thing, whatever the entries are
    called."""
    def pulse(name):
        p = dict(cfg['pulses'][name])
        if 'waveforms' in p:
            p['waveforms'] = {k: cfg['waveforms'][v]
                              for k, v in p['waveforms'].items()}
        if 'digital_marker' in p:
            p['digital_marker'] = cfg['digital_waveforms'][p['digital_marker']]
        if 'integration_weights' in p:
            p['integration_weights'] = {
                k: cfg['integration_weights'][v]
                for k, v in p['integration_weights'].items()}
        return p
    out = {}
    for name, el in cfg['elements'].items():
        e = {k: v for k, v in el.items() if k != 'operations'}
        e['operations'] = {label: pulse(pn)
                           for label, pn in el['operations'].items()}
        out[name] = e
    return out


def test_generated_config_matches_the_hand_written_golden():
    ex = _stub()
    cfg = build_opx_config(ex)
    f150, f80 = ex.raman.ao_frequencies(119.4639e6)
    gold = _golden_hand_written(hz_to_int(f80), hz_to_int(f150))

    # elements: same names, same everything but the pulse names behind ops
    assert set(cfg['elements']) == set(gold['elements'])
    for name, gel in gold['elements'].items():
        el = cfg['elements'][name]
        assert {k: v for k, v in el.items() if k != 'operations'} == \
            {k: v for k, v in gel.items() if k != 'operations'}, name
        assert set(el['operations']) == set(gel['operations']), name
    # the controller block is identical
    assert cfg['controllers'] == gold['controllers']
    # and what each op plays is identical, name indirections followed
    assert _resolved(cfg) == _resolved(gold)
    # every config section is consumed by some element (no orphans)
    used_pulses = {pn for el in cfg['elements'].values()
                   for pn in el['operations'].values()}
    assert used_pulses == set(cfg['pulses'])


def test_config_names_follow_the_quam_rule():
    cfg = build_opx_config(_stub())
    for el, ec in cfg['elements'].items():
        for label, pulse in ec['operations'].items():
            assert pulse == f"{el}.{label}.pulse"
            p = cfg['pulses'][pulse]
            if 'waveforms' in p:
                assert p['waveforms'] == {'single': f"{el}.{label}.wf"}
            if 'digital_marker' in p:
                assert p['digital_marker'] == f"{el}.{label}.dm"
            for w, wn in p.get('integration_weights', {}).items():
                assert wn == f"{el}.{label}.{w}.iw"
    assert set(cfg['pulses']) == {
        'raman_80.cw.pulse', 'raman_150.cw.pulse',
        'raman_switch.block.pulse', 'raman_switch.pass.pulse',
        'imaging_switch.block.pulse', 'imaging_switch.pass.pulse',
        'artiq_handback.trigger.pulse', 'apd.acquire.pulse'}
    assert set(cfg['integration_weights']) == {
        'apd.acquire.integration_window.iw', 'apd.acquire.full_pulse.iw'}
    # the fixture's config (what the offline simulator and the viewer tests
    # run on) is the same builder
    fc = fake_config()
    assert set(fc['pulses']) == set(cfg['pulses'])
    assert config_pulse(fc, 'apd', 'acquire')['length'] == 5000


def test_build_opx_config_guards():
    ex = _stub()
    ex.dds.raman_80_plus.amplitude = 0.6
    with pytest.raises(ValueError, match='exceeds'):
        build_opx_config(ex)
    ex = _stub()
    ex.params.t_opx_integration_len = 6.e-6          # > 5 us acquire
    with pytest.raises(ValueError, match='does not fit'):
        build_opx_config(ex)
    # the map builder validates too, so a bad value fails at opx.use()
    with pytest.raises(ValueError, match='does not fit'):
        kexp_channel_map(ex)


def test_integration_window_with_start_and_tail():
    ex = _stub()
    ex.params.t_opx_integration_start = 1.e-6
    ex.params.t_opx_integration_len = 3.e-6
    cfg = build_opx_config(ex)
    w = cfg['integration_weights']['apd.acquire.integration_window.iw']
    assert w['cosine'] == [(0.0, 1000), (1.0, 3000), (0.0, 1000)]
    assert w['sine'] == [(0.0, 1000), (0.0, 3000), (0.0, 1000)]
    assert cfg['integration_weights']['apd.acquire.full_pulse.iw']['cosine'] == [(1.0, 5000)]


# ---------------------------------------------------------------------------
# components
# ---------------------------------------------------------------------------

def test_machine_to_dict_is_json():
    m = build_machine(_stub())
    d = m.to_dict()
    text = json.dumps(d)                       # would raise on numpy / tuples
    back = json.loads(text)
    assert back['__class__'].endswith('components.Machine')
    assert back['con'] == 'con1'
    assert [e['name'] for e in back['elements']] == list(m.names)
    for e in back['elements']:
        assert '__class__' in e and e['__class__'].startswith(
            'kexp.control.opx.components.')
    assert back['elements'][0]['sticky'] == {'duration_ns': 100,
                                             'analog': True, 'digital': False}
    assert back['elements'][2]['levels'] == {'block': 1, 'pass': 0}
    assert 'qm_qua_version' in back and back['qm_qua_version'] == qm_qua_version()
    datetime.fromisoformat(back['generated'])
    assert back['extra']['config_time_params'] == list(CONFIG_TIME_PARAMS)
    # numpy in extra is fine
    m.extra['arr'] = np.array([1, 2])
    m.extra['f'] = np.float64(1.5)
    json.dumps(m.to_dict())


def test_machine_validation():
    def line(name, port=1):
        return DigitalLine(name=name, port=port, sticky=Sticky(duration_ns=16))
    with pytest.raises(ValueError, match='duplicate'):
        Machine(elements=[line('a', 1), line('a', 2)]).generate_config()
    with pytest.raises(ValueError, match='port'):
        Machine(elements=[line('a', 1), line('b', 1)]).generate_config()
    with pytest.raises(ValueError, match="'\\.'"):
        Machine(elements=[line('a.b')]).generate_config()
    with pytest.raises(ValueError, match='exceeds'):
        Machine(elements=[AnalogDrive(name='d', port=1, if_hz=1000,
                                      amplitude_v=MAX_ANALOG_V + 0.01)]
                ).generate_config()
    with pytest.raises(ValueError, match='does not fit'):
        Machine(elements=[IntegratedInput(name='i', in_port=1, marker_port=4,
                                          acquire_ns=1000, window_start_ns=0,
                                          window_len_ns=2000)]
                ).generate_config()
    with pytest.raises(ValueError, match='multiple of 4'):
        Machine(elements=[DigitalLine(name='a', port=1, edge_ns=18)]
                ).generate_config()
    with pytest.raises(KeyError):
        Machine(elements=[line('a')]).element('zz')
    # a valid machine: a shared analog INPUT is not a clash, and an element
    # on another controller gets its own controllers entry
    cfg = Machine(elements=[
        IntegratedInput(name='i1', in_port=1, marker_port=4, acquire_ns=1000,
                        window_start_ns=0, window_len_ns=1000),
        IntegratedInput(name='i2', in_port=1, marker_port=5, acquire_ns=1000,
                        window_start_ns=0, window_len_ns=1000),
        line('x', 1), DigitalLine(name='y', port=1, con='con2'),
    ]).generate_config()
    assert set(cfg['controllers']) == {'con1', 'con2'}
    assert cfg['controllers']['con1']['digital_outputs'] == {4: {}, 5: {}, 1: {}}


def test_sticky_to_config_writes_digital_only_when_set():
    assert Sticky(duration_ns=100, digital=False).to_config() == \
        {'analog': True, 'duration': 100}
    assert Sticky(duration_ns=16).to_config() == \
        {'analog': True, 'digital': True, 'duration': 16}


def test_channel_map_defaults_and_op_check():
    # a map built by hand (test_opx.make_map style) has no machine and no
    # config-time list -- both optional
    cmap = ChannelMap(channels={'raman': ChannelSpec('raman_switch')},
                      t_handoff_settle_s=1.e-6, t_handback_hold_s=1.e-6)
    assert cmap.machine is None and cmap.config_time_params == ()
    # the lab map is checked against its machine at build time: an element
    # or op the map names that the machine does not have is caught there
    from kexp.control.opx.opx_config import _check_map_against_machine
    m = build_machine(_stub())
    _check_map_against_machine(kexp_channel_map(_stub()), m)     # the real map

    def bad(channels, handback='artiq_handback'):
        return ChannelMap(channels=channels, handback_element=handback,
                          t_handoff_settle_s=1.e-6, t_handback_hold_s=1.e-6)
    with pytest.raises(ValueError, match="'open'"):
        _check_map_against_machine(
            bad({'raman': ChannelSpec('raman_switch', pass_op='open')}), m)
    with pytest.raises(ValueError, match="'nope'"):
        _check_map_against_machine(
            bad({'imaging': ChannelSpec('imaging_switch', measure_element='apd',
                                        integration_weight='nope')}), m)
    with pytest.raises(KeyError, match='no_such_element'):
        _check_map_against_machine(bad({'x': ChannelSpec('no_such_element')}), m)
    with pytest.raises(ValueError, match="'trigger'"):
        _check_map_against_machine(bad({}, handback='raman_switch'), m)


def test_offline_fixture_runs_on_the_generated_config():
    # the offline simulator resolves pulses through elements/operations, so
    # it must be indifferent to the renamed entries
    from opx_sim_fixture import trace_and_simulate, _exposures, _triggers
    from kexp.control.opx.sequence import OPXSequence

    def body(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)
    seq = OPXSequence(body, name='_cfg_sim', claims=('raman',))
    job = trace_and_simulate(seq, [('t_raman_pulse', [2.e-6, 3.e-6])],
                             duration_ns=100_000)
    rep = job.get_simulated_waveform_report()
    assert len(_triggers(rep)) == 2
    assert [w.length for w in _exposures(rep)] == [2000, 3000]
