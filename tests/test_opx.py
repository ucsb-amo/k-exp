"""Offline tests for kexp.control.opx -- everything up to (but excluding)
talking to a QOP: unit conversion, per-shot tables, trace-time validation,
program trace, config building, and container filling.

Run from the workspace root with the root venv:
    .venv/Scripts/python.exe -m pytest k-exp/tests/test_opx.py

Simulation and execution need the OPX on the network (milestone M1);
nothing here opens a socket.
"""

import os
import sys

import numpy as np
import pytest
from types import SimpleNamespace

from waxa.base.xvar import xvar
from waxx.config.data_vault import DataVault

from kexp.control.opx.units import s_to_cc, hz_to_int, demod2volts
from kexp.control.opx.params_bridge import (build_shot_tables, ParamsProxy,
                                            ParamRef)
from kexp.control.opx.sequence import OPXSequence, opx_sequence, get_sequence
from kexp.control.opx.channels import ChannelMap, ChannelSpec
from kexp.control.opx.builder import OPXProgramBuilder
from kexp.control.opx.manager import OPXManager, VALID_MASK_KEY

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opx_sim_fixture import fake_raman_expt                    # noqa: E402


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------

class FakeParams:
    def __init__(self):
        self.t_raman_pulse = 0.
        self.t_raman_pi_pulse = 8.8e-6
        self.t_fixed = 5.e-6
        self.t_opx_handoff_settle = 10.e-6
        self.t_opx_handback_overlap = 10.e-6
        self.frequency_raman_transition = 119.4639e6
        self.a_list = np.array([1., 2.])   # non-scalar: must not become a column

    def compute_derived(self):
        self.t_double = 2. * self.t_raman_pulse


class FakeExpt:
    """Duck-types what build_shot_tables needs of a waxx Expt after
    finish_prepare: scan_xvars (already repeated/shuffled), xvardims,
    params, compute_new_derived."""

    def __init__(self, xvars):
        self.params = FakeParams()
        self.p = self.params
        self.scan_xvars = [xvar(k, np.asarray(v), position=i)
                           for i, (k, v) in enumerate(xvars)]
        self.xvardims = [len(xv.values) for xv in self.scan_xvars]
        # the Raman split the OPX config and builder go through
        r = fake_raman_expt()
        self.dds, self.raman = r.dds, r.raman

    def compute_new_derived(self):
        self.params.t_new = self.params.t_raman_pulse + 1.e-6


def make_map():
    return ChannelMap(
        channels={
            'raman': ChannelSpec('raman_switch',
                                 analog_elements=('raman_80', 'raman_150')),
            'imaging': ChannelSpec('imaging_switch', measure_element='apd',
                                   t_acquire_s=5.e-6, t_integration_s=5.e-6),
        },
        sync_channel='raman',
        handback_element='artiq_handback',
        guarded_channels=('raman', 'imaging'),
        t_handoff_settle_s=10.e-6,
        t_handback_overlap_s=10.e-6)


def test_channel_map_requires_handshake_times():
    with pytest.raises(ValueError, match='t_handoff_settle_s'):
        ChannelMap(channels={}, t_handback_overlap_s=10.e-6)
    with pytest.raises(ValueError, match='t_handback_overlap_s'):
        ChannelMap(channels={}, t_handoff_settle_s=10.e-6,
                   t_handback_overlap_s=0.)


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------

def test_s_to_cc_scalar_and_array():
    assert s_to_cc(1.e-6) == 250
    assert s_to_cc(0.) == 0
    out = s_to_cc(np.array([0., 16.e-9, 1.e-6]))
    assert list(out) == [0, 4, 250]

def test_s_to_cc_rejects_sub_minimum_nonzero():
    with pytest.raises(ValueError):
        s_to_cc(8.e-9)   # 2 cc < the 4 cc minimum

def test_hz_and_volts():
    assert hz_to_int(80.e6) == 80_000_000
    # 4096 * raw / duration_ns (qualang_tools demod2volts convention)
    assert demod2volts(5000., 5.e-6) == pytest.approx(4096. * 5000. / 5000.)


# ---------------------------------------------------------------------------
# params bridge
# ---------------------------------------------------------------------------

def test_shot_tables_flat_order_and_derived():
    # 2 xvars: shots run with the LAST xvar innermost, matching the ARTIQ
    # scan loop; derived params (compute_derived and the experiment's
    # compute_new_derived) follow the scan per shot
    a = [1.e-6, 2.e-6, 3.e-6]
    b = [10., 20.]
    ex = FakeExpt([('t_raman_pulse', a), ('other', b)])
    ex.params.other = b[0]
    tables = build_shot_tables(ex)

    assert tables.n_shots == 6
    assert list(tables.column('t_raman_pulse')) == [
        1.e-6, 1.e-6, 2.e-6, 2.e-6, 3.e-6, 3.e-6]
    assert list(tables.column('other')) == [10., 20.] * 3
    assert list(tables.column('t_double')) == [
        2.e-6, 2.e-6, 4.e-6, 4.e-6, 6.e-6, 6.e-6]
    assert list(tables.column('t_new')) == [
        2.e-6, 2.e-6, 3.e-6, 3.e-6, 4.e-6, 4.e-6]
    assert tables.is_constant('t_fixed')
    assert not tables.is_constant('t_raman_pulse')
    assert not tables.has('a_list')

def test_sweep_restores_live_params():
    ex = FakeExpt([('t_raman_pulse', [1.e-6, 2.e-6])])
    before = ex.params
    build_shot_tables(ex)
    assert ex.params is before and ex.p is before
    assert ex.params.t_raman_pulse == 0.   # untouched by the sweep

def test_proxy_and_paramref_guards():
    ex = FakeExpt([('t_raman_pulse', [1.e-6, 2.e-6])])
    proxy = ParamsProxy(build_shot_tables(ex))
    ref = proxy.t_raman_pulse
    assert isinstance(ref, ParamRef)
    assert 't_raman_pulse' in dir(proxy)
    with pytest.raises(AttributeError):
        proxy.no_such_param
    with pytest.raises(AttributeError):
        proxy.a_list          # arrays cannot ship per shot
    with pytest.raises(AttributeError):
        proxy.t_raman_pulse = 1.
    with pytest.raises(ValueError):
        ref.column[0] = 0.    # a handle on the tables, never a way in
    assert list(proxy.t_raman_pulse.column) == [1.e-6, 2.e-6]


def test_paramref_arithmetic_matches_derived_params():
    # host-side arithmetic on refs is, shot for shot, what compute_derived /
    # compute_new_derived produce -- the same values without the detour
    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6, 2.e-6])])
    p = ParamsProxy(build_shot_tables(ex))
    t = p.t_raman_pulse
    assert list((2. * t).column) == list(p.t_double.column)
    assert list((t + 1.e-6).column) == list(p.t_new.column)

    # every operator, both orders, python and numpy scalars, other refs
    close = np.testing.assert_allclose
    close((t - 1.e-6).column, [-1.e-6, 0., 1.e-6])
    close((1.e-6 - t).column, [1.e-6, 0., -1.e-6])
    close((t / 2).column, [0., 0.5e-6, 1.e-6])
    close((np.float64(2.) * t).column, [0., 2.e-6, 4.e-6])
    close((np.int64(2) * t).column, [0., 2.e-6, 4.e-6])
    close((t ** 2).column, [0., 1.e-12, 4.e-12])
    close((-t).column, [0., -1.e-6, -2.e-6])
    close(abs(-t).column, [0., 1.e-6, 2.e-6])
    close((t + p.t_fixed).column, [5.e-6, 6.e-6, 7.e-6])
    close(np.maximum(t, 1.e-6).column, [1.e-6, 1.e-6, 2.e-6])
    close(np.sin(t).column, np.sin([0., 1.e-6, 2.e-6]))
    close(round(t * 1.e6).column, [0., 1., 2.])

    # comparisons are 0/1 columns (per-shot factors), not python truth
    assert list((t > 0.5e-6).column) == [0., 1., 1.]
    assert list((t == 0.).column) == [1., 0., 0.]

    # constant expressions stay constant; labels stay readable
    assert (p.t_fixed / 2).is_constant and not (t / 2).is_constant
    assert (t * 2).label == '(t_raman_pulse * 2)'
    assert np.maximum(t, 1.e-6).label == 'maximum(t_raman_pulse, 1e-06)'
    assert 'per-shot' in repr(t) and '= 5e-06' in repr(p.t_fixed)


def test_derived_dependents_found_by_perturbation():
    from kexp.control.opx.params_bridge import derived_dependents
    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6])])
    assert derived_dependents(
        ex, 't_raman_pulse', ['t_double', 't_new', 't_fixed']) == ['t_double', 't_new']
    assert derived_dependents(ex, 't_fixed', ['t_double', 't_new']) == []
    assert ex.params.t_raman_pulse == 0.        # live params untouched
    assert not hasattr(ex.params, 't_new')


def test_paramref_is_never_one_number():
    ex = FakeExpt([('t_raman_pulse', [1.e-6, 2.e-6])])
    p = ParamsProxy(build_shot_tables(ex))
    t = p.t_raman_pulse
    for bad in (lambda: float(t), lambda: int(t), lambda: bool(t),
                lambda: max(t, 1.e-6), lambda: t in [1.e-6],
                lambda: np.sum(t), lambda: np.add.reduce(t),
                lambda: t + np.array([1., 2.]),      # loose per-shot array
                lambda: t + 'x'):
        with pytest.raises(TypeError, match=r'\[opx\]'):
            bad()
    with pytest.raises(TypeError, match='traced once'):
        if t:
            pass
    # refs from another run's tables cannot be mixed in
    other = ParamsProxy(build_shot_tables(ex)).t_raman_pulse
    with pytest.raises(TypeError, match='different'):
        t + other


# ---------------------------------------------------------------------------
# sequences
# ---------------------------------------------------------------------------

def test_sequence_registry_and_bare_function_rejected():
    @opx_sequence('_t_reg', claims=('raman',))
    def s(ctx):
        pass
    assert get_sequence('_t_reg') is s
    assert get_sequence(s) is s
    with pytest.raises(TypeError):
        get_sequence(lambda ctx: None)
    with pytest.raises(KeyError):
        get_sequence('_t_nonexistent')


# ---------------------------------------------------------------------------
# builder / trace-time validation (traces real QUA; no hardware)
# ---------------------------------------------------------------------------

def _trace(seq, xvals=(0., 1.e-6, 2.e-6)):
    ex = FakeExpt([('t_raman_pulse', list(xvals))])
    tables = build_shot_tables(ex)
    builder = OPXProgramBuilder(seq, make_map(), tables, tables.n_shots)
    return builder.trace()

def test_trace_pulse_and_measure_sequence():
    @opx_sequence('_t_apd', claims=('raman', 'imaging'),
                  measurements={'sig': 2})
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)   # varies, includes 0
        ctx.raman_pulse(ctx.p.t_fixed)         # baked constant
        ctx.wait_s(3.e-6)
        ctx.measure('sig')
        ctx.measure('sig', expose=False)

    prog, ctx = _trace(s)
    assert prog is not None
    assert ctx._save_counts == {'sig': 2}
    assert ctx._stream_roles == {'sig': 'imaging'}
    assert ctx._handback_done   # auto-appended

def test_single_shot_table_slice_bakes_constants():
    # slicing the tables to one shot (simulate_shots=1) turns every scanned
    # ParamRef into a baked constant: no QUA arrays in the traced program
    from kexp.control.opx.params_bridge import ShotTables

    @opx_sequence('_t_slice', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)

    ex = FakeExpt([('t_raman_pulse', [4.e-6, 1.e-6, 2.e-6])])
    tables = build_shot_tables(ex)
    sliced = ShotTables({k: c[:1].copy() for k, c in tables.columns.items()}, 1)
    assert sliced.is_constant('t_raman_pulse')
    assert sliced.column('t_raman_pulse')[0] == 4.e-6   # first SCHEDULED shot

    _prog, ctx = OPXProgramBuilder(s, make_map(), sliced, 1).trace(
        skip_triggers=True)
    assert ctx._qua_arrays == {}


def _ctx(xvals=(0., 1.e-6, 2.e-6)):
    """A context outside any QUA program -- enough for const() and the
    host-side checks."""
    from kexp.control.opx.context import OPXShotContext
    ex = FakeExpt([('t_raman_pulse', list(xvals))])
    tables = build_shot_tables(ex)
    seq = OPXSequence(lambda ctx: None, name='_t_ctx')
    return OPXShotContext(make_map(), tables, seq, None, 0, [])

def test_ctx_const_reads_run_level_constants_only():
    ctx = _ctx()
    v = ctx.const(ctx.p.t_fixed)
    assert v == 5.e-6 and isinstance(v, float)
    assert ctx.const(3) == 3.
    assert ctx.const(ctx.p.t_fixed / 2) == 2.5e-6
    with pytest.raises(RuntimeError, match='varies per shot'):
        ctx.const(ctx.p.t_raman_pulse)
    with pytest.raises(RuntimeError, match='varies per shot'):
        ctx.const(ctx.p.t_double)          # derived from a scanned param
    with pytest.raises(TypeError):
        ctx.const(np.array([1., 2.]))

def test_trace_expressions_bake_or_share_qua_arrays():
    @opx_sequence('_t_expr', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse * 2)     # per shot -> QUA array
        ctx.raman_pulse(2 * ctx.p.t_raman_pulse)     # same values -> shared
        ctx.raman_pulse(ctx.p.t_fixed / 2)           # constant -> baked
        ctx.wait_s(ctx.p.t_raman_pulse + 1.e-6)      # a second array

    _prog, ctx = _trace(s, xvals=(0., 1.e-6, 2.e-6))
    assert sorted(ctx._qua_arrays) == [('cc', (0, 500, 1000)),
                                       ('cc', (250, 500, 750))]

def test_trace_rejects_nan_range_and_loose_arrays():
    @opx_sequence('_t_nan', claims=('raman',))
    def s_nan(ctx):
        with np.errstate(divide='ignore'):
            t = 1.e-12 / ctx.p.t_raman_pulse   # inf where t = 0
        ctx.raman_pulse(t)
    with pytest.raises(ValueError, match='inf'):
        _trace(s_nan)

    @opx_sequence('_t_fixed', claims=('raman',))
    def s_fixed(ctx):
        ctx.f(ctx.p.t_raman_pulse * 1.e7)     # 0, 10, 20: outside [-8, 8)
    with pytest.raises(ValueError, match='fixed-point'):
        _trace(s_fixed)

    @opx_sequence('_t_arr', claims=('raman',))
    def s_arr(ctx):
        ctx.raman_pulse(np.array([1.e-6, 2.e-6, 3.e-6]))
    with pytest.raises(TypeError, match='number or a ctx.p'):
        _trace(s_arr)

    @opx_sequence('_t_big', claims=('raman',))
    def s_big(ctx):
        ctx.wait_s(100.)                      # 100 s: the delay(100) slip
    with pytest.raises(ValueError, match='32-bit'):
        _trace(s_big)

def test_trace_skip_triggers_for_simulation():
    @opx_sequence('_t_sim', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)
    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6])])
    tables = build_shot_tables(ex)
    builder = OPXProgramBuilder(s, make_map(), tables, tables.n_shots)
    from qm import generate_qua_script
    src_real = generate_qua_script(builder.trace()[0])
    src_sim = generate_qua_script(builder.trace(skip_triggers=True)[0])
    assert 'wait_for_trigger' in src_real
    assert 'wait_for_trigger' not in src_sim

def test_trace_generates_qua_source():
    from qm import generate_qua_script
    from kexp.control.opx.opx_config import build_opx_config

    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6])])
    ex.params.t_imaging_pulse_apd_abs = 5.e-6
    ex.params.t_opx_integration_start = 0.
    ex.params.t_opx_integration_len = 5.e-6

    @opx_sequence('_t_src', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)

    tables = build_shot_tables(ex)
    prog, _ctx = OPXProgramBuilder(s, make_map(), tables,
                                   tables.n_shots).trace()
    config = build_opx_config(ex)
    src = generate_qua_script(prog, config)
    for token in ('wait_for_trigger', 'raman_switch', 'artiq_handback'):
        assert token in src

def test_trace_settles_before_the_body():
    # ARTIQ turns its RF on halfway through t_opx_handoff_settle: the body's
    # first exposure must come after the settle wait, and the wait after the
    # trigger and the block plays
    from qm import generate_qua_script

    @opx_sequence('_t_settle', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_fixed)

    prog, _ctx = _trace(s)
    src = generate_qua_script(prog)
    i_trigger = src.index("wait_for_trigger('raman_switch')")
    i_block = src.index("play('block', 'raman_switch')", i_trigger)
    i_settle = src.index("wait(2500, 'raman_switch')", i_block)   # 10 us
    i_expose = src.index("play('pass', 'raman_switch', duration=1250)",
                         i_settle)
    assert i_trigger < i_block < i_settle < i_expose

def test_trace_records_accessed_params():
    @opx_sequence('_t_acc', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)
        ctx.wait_s(ctx.p.t_fixed)

    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6])])
    tables = build_shot_tables(ex)
    OPXProgramBuilder(s, make_map(), tables, tables.n_shots).trace()
    assert tables.accessed == {'t_raman_pulse', 't_fixed'}

def test_live_adjust_of_a_baked_param_is_refused():
    # the OPX bakes its per-shot values at finish_prepare; the Adjust panel
    # must not be able to move a parameter the sequence read, directly or
    # through a derived quantity
    from kexp.control.opx.manager import check_live_adjust_conflicts

    @opx_sequence('_t_adj', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_double)          # derived from t_raman_pulse

    ex = FakeExpt([('t_fixed', [5.e-6, 6.e-6])])
    tables = build_shot_tables(ex)
    OPXProgramBuilder(s, make_map(), tables, tables.n_shots).trace()

    ex._adjust_specs = [SimpleNamespace(key='t_raman_pi_pulse')]   # unrelated
    check_live_adjust_conflicts(ex, tables)
    ex._adjust_specs = [SimpleNamespace(key='t_double')]           # read directly
    with pytest.raises(RuntimeError, match=r'reads ctx\.p\.t_double'):
        check_live_adjust_conflicts(ex, tables)
    ex._adjust_specs = [SimpleNamespace(key='t_raman_pulse')]      # feeds t_double
    with pytest.raises(RuntimeError, match='derive from it'):
        check_live_adjust_conflicts(ex, tables)

def test_measure_count_mismatch_is_an_error():
    @opx_sequence('_t_count', claims=('imaging',), measurements={'sig': 3})
    def s(ctx):
        ctx.measure('sig')
    with pytest.raises(RuntimeError, match='declares 3'):
        _trace(s)

def test_unclaimed_channel_is_an_error():
    @opx_sequence('_t_claim', claims=())
    def s(ctx):
        ctx.raman_pulse(1.e-6)
    with pytest.raises(RuntimeError, match='without claiming'):
        _trace(s)

def test_double_handback_is_an_error():
    @opx_sequence('_t_hb2', claims=('raman',))
    def s(ctx):
        ctx.handback_to_artiq()
        ctx.handback_to_artiq()
    with pytest.raises(RuntimeError, match='more than once'):
        _trace(s)

def test_nothing_after_handback():
    @opx_sequence('_t_after', claims=('raman',))
    def s(ctx):
        ctx.handback_to_artiq()
        ctx.raman_pulse(1.e-6)
    with pytest.raises(RuntimeError, match='after'):
        _trace(s)

def test_undeclared_measure_key_is_an_error():
    @opx_sequence('_t_key', claims=('imaging',), measurements={'sig': 1})
    def s(ctx):
        ctx.measure('wrong_key')
    with pytest.raises(RuntimeError, match='not declared'):
        _trace(s)


# ---------------------------------------------------------------------------
# container filling (execution order in, xvardims + NaN + mask out)
# ---------------------------------------------------------------------------

def _stub_with_containers(n_shots, n_per_shot):
    stub = FakeExpt([('t_raman_pulse', np.linspace(0., 1.e-6, n_shots))])
    data = DataVault(expt=stub)
    data.sig = data.add_data_container((n_per_shot,), np.float64)
    setattr(data, VALID_MASK_KEY, data.add_data_container((1,), np.int32))
    data.init()
    stub.data = data
    return stub

def test_fill_containers_complete_run():
    stub = _stub_with_containers(n_shots=4, n_per_shot=2)
    seq = OPXSequence(lambda ctx: None, name='_t_fill',
                      measurements={'sig': 2})
    raw = np.arange(8.).reshape(4, 2)
    OPXManager.fill_containers(stub, seq, make_map(), {'sig': 'imaging'},
                               {'sig': raw}, {'sig': 4}, 4)
    v = stub.data.sig._run_data
    assert v.shape == (4, 2)
    # volts conversion: 4096 * raw / 5000 ns
    assert v == pytest.approx(4096. * raw / 5000.)
    assert stub.data.sig._data_gotten
    mask = getattr(stub.data, VALID_MASK_KEY)._run_data
    assert list(mask) == [1, 1, 1, 1]

def test_fill_containers_partial_run_nans_and_flags():
    stub = _stub_with_containers(n_shots=5, n_per_shot=1)
    seq = OPXSequence(lambda ctx: None, name='_t_fill2',
                      measurements={'sig': 1})
    raw = np.array([1., 2., 3.])
    OPXManager.fill_containers(stub, seq, make_map(), {'sig': 'imaging'},
                               {'sig': raw}, {'sig': 3}, 5)
    v = stub.data.sig._run_data
    assert v.shape == (5,)
    assert np.all(np.isfinite(v[:3])) and np.all(np.isnan(v[3:]))
    mask = getattr(stub.data, VALID_MASK_KEY)._run_data
    assert list(mask) == [1, 1, 1, 0, 0]


# ---------------------------------------------------------------------------
# kexp config
# ---------------------------------------------------------------------------

def _config_stub(a_80=0.337, frequency_raman_transition=119.4639e6):
    ex = fake_raman_expt(a_80=a_80, a_150=0.324,
                         frequency_raman_transition=frequency_raman_transition)
    p = ex.params
    p.t_imaging_pulse_apd_abs = 5.e-6
    p.t_opx_integration_start = 0.
    p.t_opx_integration_len = 5.e-6
    p.t_opx_handoff_settle = 10.e-6
    p.t_opx_handback_overlap = 10.e-6
    return ex

def test_build_opx_config_shape():
    from kexp.control.opx.opx_config import build_opx_config
    cfg = build_opx_config(_config_stub())
    els = cfg['elements']
    for el in ('raman_80', 'raman_150', 'raman_switch', 'imaging_switch',
               'artiq_handback', 'apd'):
        assert el in els
    # IFs at the Raman resonance, split like the kernel -- not the dds
    # centers (80/150 MHz is the 140 MHz two-photon point)
    f150, f80 = _config_stub().raman.ao_frequencies(119.4639e6)
    assert els['raman_80']['intermediate_frequency'] == hz_to_int(f80)
    assert els['raman_150']['intermediate_frequency'] == hz_to_int(f150)
    assert els['raman_80']['intermediate_frequency'] != 80_000_000
    assert cfg['waveforms']['raman_80_wf']['sample'] == 0.337
    assert cfg['pulses']['apd_acquire']['length'] == 5000
    # integration window covers exactly the acquire length
    w = cfg['integration_weights']['integration_window']['cosine']
    assert sum(ns for _v, ns in w) == 5000

def test_kexp_channel_map_reads_handshake_params():
    from kexp.control.opx.opx_config import kexp_channel_map
    cmap = kexp_channel_map(_config_stub())
    assert cmap.t_handoff_settle_s == 10.e-6
    assert cmap.t_handback_overlap_s == 10.e-6
    assert cmap.guarded_channels == ('raman', 'imaging')

def test_build_opx_config_amp_guard():
    from kexp.control.opx.opx_config import build_opx_config
    with pytest.raises(ValueError, match='exceeds'):
        build_opx_config(_config_stub(a_80=0.6))

def test_integration_window_must_fit():
    from kexp.control.opx.opx_config import build_opx_config
    ex = _config_stub()
    ex.params.t_opx_integration_len = 6.e-6   # > 5 us acquire
    with pytest.raises(ValueError, match='does not fit'):
        build_opx_config(ex)


# ---------------------------------------------------------------------------
# Raman transition -> OPX drive IFs (shared split with the ARTIQ kernel)
# ---------------------------------------------------------------------------

F_TR = 119.4639e6

def make_transition_map(ex):
    from kexp.control.opx.opx_config import (raman_transition_to_ifs,
                                             RAMAN_TRANSITION_PARAM)
    cmap = make_map()
    spec = cmap.channels['raman']
    spec.transition_param = RAMAN_TRANSITION_PARAM
    spec.transition_to_ifs = raman_transition_to_ifs(ex)
    return cmap

def test_ao_frequencies_is_the_kernel_split():
    pair = fake_raman_expt().raman
    dummy = pair._dummy.copy()
    f150, f80 = pair.ao_frequencies(F_TR)
    # both +1 order double-pass AOs: two-photon = 2 * (f150 - f80)
    assert abs(2. * (f150 - f80) - F_TR) < 1.e-3
    assert abs(f150 - 143.303446e6) < 10. and abs(f80 - 83.571496e6) < 10.
    # arrays: elementwise identical to the kernel method called per value
    fs = np.array([F_TR, F_TR + 5.e3, F_TR - 2.e6])
    a150, a80 = pair.ao_frequencies(fs)
    for f, x150, x80 in zip(fs, a150, a80):
        pair.state_splitting_to_ao_frequency(f)
        assert (x150, x80) == (pair._dummy[0], pair._dummy[1])
    pair._dummy[:] = dummy
    pair.ao_frequencies(fs)
    np.testing.assert_array_equal(pair._dummy, dummy)   # scratch restored

def test_raman_ifs_refuse_miswired_pair():
    from kexp.control.opx.opx_config import raman_transition_to_ifs
    ex = fake_raman_expt()
    ex.raman.dds0 = SimpleNamespace()        # 150 no longer in the pair
    with pytest.raises(RuntimeError, match='not part of expt.raman'):
        raman_transition_to_ifs(ex)

def test_config_ifs_follow_first_executed_shot():
    from kexp.control.opx.opx_config import build_opx_config
    ex = FakeExpt([('frequency_raman_transition', [F_TR + 1.e6, F_TR])])
    ex.params.t_imaging_pulse_apd_abs = 5.e-6
    ex.params.t_opx_integration_start = 0.
    ex.params.t_opx_integration_len = 5.e-6
    tables = build_shot_tables(ex)
    cfg = build_opx_config(ex, tables)
    f150, f80 = ex.raman.ao_frequencies(F_TR + 1.e6)
    assert cfg['elements']['raman_150']['intermediate_frequency'] ==         hz_to_int(f150)
    assert cfg['elements']['raman_80']['intermediate_frequency'] ==         hz_to_int(f80)
    assert 'frequency_raman_transition' in tables.accessed

def _trace_transition(seq, xvars):
    ex = FakeExpt(xvars)
    tables = build_shot_tables(ex)
    b = OPXProgramBuilder(seq, make_transition_map(ex), tables,
                          tables.n_shots)
    prog, ctx = b.trace()
    return ex, tables, b, prog, ctx

def test_constant_transition_adds_no_frequency_updates():
    from qm import generate_qua_script

    @opx_sequence('_t_tr_const', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)

    _ex, _t, _b, prog, _ctx = _trace_transition(
        s, [('t_raman_pulse', [0., 1.e-6])])
    assert 'update_frequency' not in generate_qua_script(prog)

def test_scanned_transition_repoints_drives_every_shot():
    from qm import generate_qua_script

    @opx_sequence('_t_tr_scan', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_fixed)

    fs = [F_TR - 1.e3, F_TR, F_TR + 1.e3]
    ex, tables, b, prog, _ctx = _trace_transition(
        s, [('frequency_raman_transition', fs)])
    src = generate_qua_script(prog)
    i_upd = src.index("update_frequency('raman_150'")
    assert "update_frequency('raman_80'" in src
    assert i_upd < src.index('wait_for_trigger')     # before the handoff
    recs = [r for r in b.log.records if r.kind == 'update_frequency']
    assert {r.macro for r in recs} == {'transition'}
    col = tables.column('frequency_raman_transition')
    f150, f80 = ex.raman.ao_frequencies(col)
    by_el = {r.element: r.extra['frequency_hz'] for r in recs}
    np.testing.assert_array_equal(by_el['raman_150'], hz_to_int(f150))
    np.testing.assert_array_equal(by_el['raman_80'], hz_to_int(f80))

def test_set_transition_in_body_is_restored_after_the_shot():
    from qm import generate_qua_script

    @opx_sequence('_t_tr_ramsey', claims=('raman',))
    def s(ctx):
        ctx.set_transition('raman', ctx.p.frequency_raman_transition
                           + ctx.p.t_raman_pulse * 1.e9)   # "detuning"
        ctx.raman_pulse(ctx.p.t_fixed)

    _ex, _t, b, prog, _ctx = _trace_transition(
        s, [('t_raman_pulse', [0., 1.e-6])])
    src = generate_qua_script(prog)
    i_body = src.index("update_frequency('raman_150'")
    i_handback = src.index("'artiq_handback'")
    i_restore = src.index("update_frequency('raman_150'", i_handback)
    assert i_body < i_handback < i_restore
    macros = [r.macro for r in b.log.records if r.kind == 'update_frequency']
    assert macros.count('set_transition') == 2
    assert macros.count('transition_restore') == 2

def test_set_transition_needs_claim_and_split():
    @opx_sequence('_t_tr_unclaimed', claims=('imaging',))
    def s1(ctx):
        ctx.set_transition('raman', 1.e8)
    with pytest.raises(RuntimeError, match='without claiming'):
        _trace_transition(s1, [('t_raman_pulse', [0.])])

    @opx_sequence('_t_tr_nosplit', claims=('imaging',))
    def s2(ctx):
        ctx.set_transition('imaging', 1.e8)
    with pytest.raises(RuntimeError, match='no transition_to_ifs'):
        _trace_transition(s2, [('t_raman_pulse', [0.])])
