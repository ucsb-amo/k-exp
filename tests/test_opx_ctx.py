"""Offline tests for the phase-2 OPX context / builder / manager additions
(design spec section 3): the raw-QUA layer (ctx.qua, ctx.shot, QUA
expressions through the macros), phase-reset pulses, timestamp streams,
ctx.save / ctx.for_range save counting, shot arrays, host data, named
aligns and raw waits, set_transition_offset, the shot-index echo, the
config-time xvar guard, 2-D / int containers, provenance texts, and the
re-entrant finish().

Run from the workspace root with the root venv:
    .venv/Scripts/python.exe -m pytest k-exp/tests/test_opx_ctx.py -q

Nothing here opens a socket: the manager's QMM connection is monkeypatched
out where a manager is driven.
"""

import json
import os
import re
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from waxx.config.data_vault import DataVault

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_opx import FakeExpt, make_map, make_transition_map, F_TR   # noqa: E402

from kexp.control.opx.params_bridge import build_shot_tables          # noqa: E402
from kexp.control.opx.sequence import (OPXSequence, opx_sequence, Stream,  # noqa: E402
                                       resolve_stream)
from kexp.control.opx.builder import OPXProgramBuilder, SHOT_INDEX_KEY  # noqa: E402
from kexp.control.opx.manager import (OPXManager, VALID_MASK_KEY,      # noqa: E402
                                      INT_MISSING, check_config_time_xvars,
                                      SHOT_TABLES_ATTR, MACHINE_ATTR,
                                      QUA_SOURCE_ATTR)
from kexp.control.opx.context import (TIMESTAMP_SKIPPED, ShotArray,   # noqa: E402
                                      is_qua_expr)
from kexp.control.opx.units import hz_to_int                          # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _qua(prog):
    from qm import generate_qua_script
    src = generate_qua_script(prog)
    return src[src.index('with program()'):src.index('config = None')]


def _stmts(src):
    return [ln.strip() for ln in src.splitlines() if ln.strip()]


def _trace(seq, xvars=None, cmap=None, setup=None):
    ex = FakeExpt(xvars or [('t_raman_pulse', [0., 1.e-6, 2.e-6])])
    if setup is not None:
        setup(ex)
    tables = build_shot_tables(ex)
    b = OPXProgramBuilder(seq, cmap or make_map(), tables, tables.n_shots)
    prog, ctx = b.trace()
    return ex, tables, b, prog, ctx


class ManagerStub(FakeExpt):
    """FakeExpt plus what OPXManager.use / on_finish_prepare / finish read."""

    def __init__(self, xvars):
        super().__init__(xvars)
        self.xvarnames = [xv.key for xv in self.scan_xvars]
        self.data = DataVault(expt=self)
        self.run_info = SimpleNamespace(save_data=False)
        self._extra_file_texts = {}
        self._shot_complete_count = int(np.prod(self.xvardims))


def _manager(stub, cmap=None, config=None, monkeypatch=None):
    m = OPXManager(stub, host='none', cluster='none',
                   map_builder=(lambda e: cmap) if cmap is not None
                   else (lambda e: make_map()),
                   config_builder=config or (lambda e, t: {}))
    if monkeypatch is not None:
        monkeypatch.setattr(OPXManager, '_connect', lambda self: None)
    return m


def _stub_with(n_shots, containers):
    """containers: {key: (shape, dtype)}; mask + echo added."""
    stub = ManagerStub([('t_raman_pulse', np.linspace(0., 1.e-6, n_shots))])
    for key, (shape, dtype) in containers.items():
        setattr(stub.data, key, stub.data.add_data_container(shape, dtype))
    setattr(stub.data, VALID_MASK_KEY,
            stub.data.add_data_container((1,), np.int32))
    setattr(stub.data, SHOT_INDEX_KEY,
            stub.data.add_data_container((1,), np.int32))
    stub.data.init()
    return stub


# ---------------------------------------------------------------------------
# sequence declarations (3.4)
# ---------------------------------------------------------------------------

def test_stream_specs_and_callables():
    assert Stream(4) == Stream((4,)) and Stream(4).dtype is float
    assert Stream((2, 3), int).n == 6 and Stream((2, 3), int).np_dtype is np.int64
    assert Stream(2, np.int64).dtype is int and Stream(2, 'float').dtype is float
    assert resolve_stream(3) == Stream((3,))
    assert resolve_stream((2, 5)) == Stream((2, 5))
    assert resolve_stream(lambda p: p.N, SimpleNamespace(N=3)) == Stream((3,))
    assert resolve_stream(lambda p: Stream((p.N, 2), int),
                          SimpleNamespace(N=3)) == Stream((3, 2), int)
    with pytest.raises(RuntimeError, match='no params'):
        resolve_stream(lambda p: p.N, None)
    for bad in (0, (2, 0), (1, 2, 3), 2.5, 'x', True):
        with pytest.raises((ValueError, TypeError)):
            Stream(bad)
    with pytest.raises(ValueError, match='both'):
        OPXSequence(lambda ctx: None, name='_c_dup', measurements={'a': 1},
                    host_data={'a': 1})
    with pytest.raises(TypeError, match='finish'):
        OPXSequence(lambda ctx: None, name='_c_fin', finish=3)
    with pytest.raises(ValueError):
        OPXSequence(lambda ctx: None, name='_c_shape', measurements={'a': 0})
    seq = OPXSequence(lambda ctx: None, name='_c_res',
                      measurements={'a': lambda p: p.N_pulses, 'b': 2},
                      host_data={'h': lambda p: (p.N_pulses, 2)})
    assert seq.resolve_measurements(SimpleNamespace(N_pulses=4)) == {
        'a': Stream((4,)), 'b': Stream((2,))}
    assert seq.resolve_host_data(SimpleNamespace(N_pulses=4)) == {
        'h': Stream((4, 2))}


def test_builder_resolves_callable_shapes_from_the_tables():
    # without live params the builder reads run-constant columns; a varying
    # one is refused (a per-shot data shape must be fixed for the run)
    @opx_sequence('_c_tabview', claims=('imaging',),
                  measurements={'sig': lambda p: p.N_pulses})
    def s(ctx):
        for _ in range(int(ctx.const(ctx.p.N_pulses))):
            ctx.measure('sig')

    def setup(ex):
        ex.params.N_pulses = 2
    ex, tables, b, prog, ctx = _trace(s, setup=setup)
    assert b.measurements == {'sig': Stream((2,))}
    assert ctx._save_counts == {'sig': 2}

    ex = FakeExpt([('N_pulses', [1, 2])])
    ex.params.N_pulses = 1
    tables = build_shot_tables(ex)
    with pytest.raises(RuntimeError, match='varies per shot'):
        OPXProgramBuilder(s, make_map(), tables, tables.n_shots)


# ---------------------------------------------------------------------------
# raw-QUA layer
# ---------------------------------------------------------------------------

def test_ctx_qua_shot_and_qua_expr_passthrough():
    @opx_sequence('_c_raw', claims=('raman',))
    def s(ctx):
        from qm import qua
        assert ctx.qua is qua
        assert ctx.n_shots == 3
        assert is_qua_expr(ctx.shot)
        v = ctx.qua.declare(int, value=500)
        assert ctx.cc(v) is v and ctx.hz(v) is v
        with pytest.raises(TypeError, match='QUA expression'):
            ctx.const(v)
        ctx.raman_pulse(v)                     # QUA duration -> if_ guard
        ctx.raman_pulse(v + ctx.shot * 4)      # any QUA int expression

    _ex, _t, _b, prog, ctx = _trace(s)
    src = _qua(prog)
    assert "with if_((v2>=4)):" in src
    assert "play('pass', 'raman_switch', duration=v2)" in src
    assert "duration=(v2+(v1*4))" in src
    pulses = [r for r in ctx.log.records if r.macro == 'raman_pulse'
              and r.kind == 'play' and r.op == 'pass']
    assert all(r.duration_cc is None and r.executes is None for r in pulses)


def test_ctx_for_range_counts_saves():
    @opx_sequence('_c_for', claims=('raman',),
                  measurements={'x': 3, 'y': Stream((2, 3)), 'z': 1})
    def s(ctx):
        w = ctx.qua.declare(ctx.qua.fixed, value=0.5)
        with ctx.for_range(3) as i:
            ctx.save('x', w)
        with ctx.for_range(2) as i:
            with ctx.for_range(3) as j:
                ctx.save('y', w)
        ctx.save('z', w)

    _ex, _t, b, prog, ctx = _trace(s)
    assert ctx._save_counts == {'x': 3, 'y': 6, 'z': 1}
    src = _qua(prog)
    assert src.count('with for_(') == 4          # shot loop + 3
    assert re.search(r"r\d+\.buffer\(3\)\.buffer\(2\)\.save_all\(\"y\"\)", src)
    assert re.search(r"r\d+\.buffer\(3\)\.save_all\(\"x\"\)", src)
    # records traced inside a loop carry the execution multiplicity
    saves = [r for r in b.log.records if r.kind == 'save' and r.data_key == 'y']
    assert len(saves) == 1 and saves[0].extra['loop'] == 6
    heads = [r for r in b.log.records if r.kind == 'for']
    assert [r.extra['count'] for r in heads] == [3, 2, 3]

    @opx_sequence('_c_for_bad', claims=('raman',), measurements={'x': 3})
    def s_bad(ctx):
        w = ctx.qua.declare(ctx.qua.fixed, value=0.5)
        with ctx.for_range(2):
            ctx.save('x', w)
    with pytest.raises(RuntimeError, match='declares 3'):
        _trace(s_bad)

    @opx_sequence('_c_for_param', claims=('raman',),
                  measurements={'x': lambda p: p.N_pulses})
    def s_param(ctx):
        w = ctx.qua.declare(ctx.qua.fixed, value=0.5)
        with ctx.for_range(ctx.p.N_pulses):      # run-constant ParamRef
            ctx.save('x', w)
    _ex, _t, _b, _p, ctx = _trace(
        s_param, setup=lambda ex: setattr(ex.params, 'N_pulses', 4))
    assert ctx._save_counts == {'x': 4}

    @opx_sequence('_c_for_var', claims=('raman',), measurements={'x': 1})
    def s_var(ctx):
        with ctx.for_range(ctx.p.t_raman_pulse * 1.e6):
            pass
    with pytest.raises(RuntimeError, match='varies per shot'):
        _trace(s_var)

    @opx_sequence('_c_for_zero', claims=('raman',), measurements={'x': 1})
    def s_zero(ctx):
        with ctx.for_range(0):
            pass
    with pytest.raises(ValueError, match='positive'):
        _trace(s_zero)


def test_ctx_save_and_stream_need_declared_keys():
    @opx_sequence('_c_save_undecl', claims=('raman',), measurements={'x': 1})
    def s(ctx):
        ctx.save('nope', ctx.shot)
    with pytest.raises(RuntimeError, match='not declared'):
        _trace(s)

    @opx_sequence('_c_stream_same', claims=('raman',), measurements={'x': 2})
    def s2(ctx):
        a = ctx.stream('x')
        assert ctx.stream('x') is a
        ctx.save('x', ctx.shot)
        ctx.save('x', 7)                          # a literal is fine too
    _ex, _t, _b, prog, ctx = _trace(s2)
    assert ctx._save_counts == {'x': 2}
    assert "save(v1, r" in _qua(prog) and "save(7, r" in _qua(prog)


# ---------------------------------------------------------------------------
# pulses: phase reset, timestamps
# ---------------------------------------------------------------------------

def test_phase_reset_pulse_statement_order():
    @opx_sequence('_c_reset', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_fixed, phase_reset=True)      # constant
        ctx.raman_pulse(ctx.p.t_raman_pulse, phase_reset=True)  # per shot

    _ex, _t, b, prog, ctx = _trace(s)
    st = _stmts(_qua(prog))
    i = st.index("reset_if_phase('raman_80')")
    assert st[i:i + 5] == [
        "reset_if_phase('raman_80')",
        "reset_if_phase('raman_150')",
        "align('raman_80', 'raman_150', 'raman_switch')",
        "play('pass', 'raman_switch', duration=1250)",
        "play('block', 'raman_switch')"]
    # the per-shot one sits inside its guard, same order, nothing between
    j = st.index("reset_if_phase('raman_80')", i + 1)
    assert st[j - 1].startswith("with if_((a1[v1]>=4))")
    assert st[j:j + 4] == [
        "reset_if_phase('raman_80')",
        "reset_if_phase('raman_150')",
        "align('raman_80', 'raman_150', 'raman_switch')",
        "play('pass', 'raman_switch', duration=a1[v1])"]
    recs = [r for r in b.log.records if r.macro == 'raman_pulse']
    kinds = [r.kind for r in recs]
    assert kinds == ['reset_if_phase', 'reset_if_phase', 'align', 'play',
                     'play', 'if', 'reset_if_phase', 'reset_if_phase',
                     'align', 'play', 'play']
    aligns = [r for r in recs if r.kind == 'align']
    assert all(r.extra['elements'] == ['raman_80', 'raman_150', 'raman_switch']
               for r in aligns)
    # guarded shots: the reset/align inside the if_ know they are skipped
    assert list(recs[6].executes) == [False, True, True]

    @opx_sequence('_c_reset_noanalog', claims=('imaging',))
    def s_bad(ctx):
        ctx._expose('imaging', 1.e-6, phase_reset=True)
    with pytest.raises(RuntimeError, match='no analog drives'):
        _trace(s_bad)


def test_timestamp_stream_counts_as_save():
    @opx_sequence('_c_ts', claims=('raman', 'imaging'),
                  measurements={'sig': 1, 't_p': Stream(1, int),
                                't_m': Stream(1, int), 't_i': Stream(1, int)})
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_fixed, timestamp_key='t_p')
        v = ctx.measure('sig', timestamp_key='t_m')
        assert is_qua_expr(v)
        ctx.imaging_pulse(ctx.p.t_fixed, timestamp_key='t_i')

    _ex, _t, b, prog, ctx = _trace(s)
    assert ctx._save_counts == {'sig': 1, 't_p': 1, 't_m': 1, 't_i': 1}
    assert ctx._stream_roles == {'sig': 'imaging'}    # timestamps: no volts
    src = _qua(prog)
    assert re.search(r"play\('pass', 'raman_switch', duration=1250, "
                     r"timestamp_stream=r\d+\)", src)
    assert re.search(r"measure\('acquire', 'apd', integration\.full\("
                     r"\"integration_window\", v\d+, \"out1\"\), "
                     r"timestamp_stream=r\d+\)", src)
    assert re.search(r"play\('pass', 'imaging_switch', duration=1250, "
                     r"timestamp_stream=r\d+\)", src)
    for key in ('t_p', 't_m', 't_i', 'sig'):
        assert re.search(r"r\d+\.buffer\(1\)\.save_all\(\"%s\"\)" % key, src)
    assert 'else_' not in src

    # a per-shot duration that is 0 on some shot: the skipped branch saves
    # the placeholder so the stream keeps one entry per shot
    @opx_sequence('_c_ts_guard', claims=('raman',),
                  measurements={'t_p': Stream(1, int)})
    def s_g(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse, timestamp_key='t_p')
    _ex, _t, b, prog, ctx = _trace(s_g)
    st = _stmts(_qua(prog))
    k = st.index("with else_():")
    assert re.fullmatch(rf"save\({TIMESTAMP_SKIPPED}, r\d+\)", st[k + 1])
    assert ctx._save_counts == {'t_p': 1}
    ph = [r for r in b.log.records if r.kind == 'save' and r.data_key == 't_p']
    assert len(ph) == 1 and list(ph[0].executes) == [True, False, False]

    @opx_sequence('_c_ts_float', claims=('raman',), measurements={'t': 1})
    def s_f(ctx):
        ctx.raman_pulse(ctx.p.t_fixed, timestamp_key='t')
    with pytest.raises(RuntimeError, match='int stream'):
        _trace(s_f)

    @opx_sequence('_c_ts_undecl', claims=('raman',))
    def s_u(ctx):
        ctx.raman_pulse(ctx.p.t_fixed, timestamp_key='t')
    with pytest.raises(RuntimeError, match='not declared'):
        _trace(s_u)

    @opx_sequence('_c_ts_zero', claims=('raman',),
                  measurements={'t': Stream(1, int)})
    def s_z(ctx):
        ctx.raman_pulse(0., timestamp_key='t')
    with pytest.raises(RuntimeError, match='zero-length'):
        _trace(s_z)

    @opx_sequence('_c_meas_int', claims=('imaging',),
                  measurements={'t': Stream(1, int)})
    def s_mi(ctx):
        ctx.measure('t')
    with pytest.raises(RuntimeError, match='int stream'):
        _trace(s_mi)

    @opx_sequence('_c_ts_both', claims=('imaging',),
                  measurements={'sig': 1, 't': Stream(1, int)})
    def s_b(ctx):
        ctx.measure('sig')
        ctx.imaging_pulse(ctx.p.t_fixed, timestamp_key='sig')
    with pytest.raises(RuntimeError, match='int stream'):   # float key
        _trace(s_b)


def test_measure_returns_variable_usable_downstream():
    @opx_sequence('_c_meas_var', claims=('imaging',),
                  measurements={'sig': 1, 'cp': 1})
    def s(ctx):
        v = ctx.measure('sig')
        w = ctx.qua.declare(ctx.qua.fixed)
        ctx.qua.assign(w, v * 0.5)
        ctx.save('cp', w)
    _ex, _t, _b, prog, ctx = _trace(s)
    assert ctx._save_counts == {'sig': 1, 'cp': 1}
    assert re.search(r"assign\(v\d+, \(v\d+\*0\.5\)\)", _qua(prog))


# ---------------------------------------------------------------------------
# shot arrays, host data
# ---------------------------------------------------------------------------

def test_shot_array_indexing_and_provenance():
    table = np.array([[250, 500], [300, 600], [350, 700]])

    @opx_sequence('_c_sa', claims=('raman',))
    def s(ctx):
        d = ctx.shot_array('d', table, dtype=int)
        assert isinstance(d, ShotArray) and d.M == 2 and d.n_shots == 3
        assert d.key == 'd' and d.dtype is int
        np.testing.assert_array_equal(d.values, table)
        with pytest.raises(ValueError):
            d.values[0, 0] = 1
        ctx.raman_pulse(d.at(1))
        with ctx.for_range(2) as i:
            ctx.raman_pulse(d.at(i))
        w = ctx.shot_array('w', [0.1, 0.2, 0.3])          # M == 1, fixed
        assert w.M == 1
        ctx.frame_rotation('raman', w.at(0))
        with pytest.raises(IndexError):
            d.at(2)
        with pytest.raises(IndexError):
            w.at(1)
        with pytest.raises(TypeError):
            d.at(1.5)
        with pytest.raises(RuntimeError, match='twice'):
            ctx.shot_array('d', table, dtype=int)

    _ex, _t, _b, prog, ctx = _trace(s)
    src = _qua(prog)
    assert "declare(int, value=[250, 500, 300, 600, 350, 700])" in src
    assert "declare(fixed, value=[0.1, 0.2, 0.3])" in src
    assert re.search(r"duration=a\d+\[\(\(v1\*2\)\+1\)\]", src)
    assert re.search(r"duration=a\d+\[\(\(v1\*2\)\+v\d+\)\]", src)
    assert re.search(r"frame_rotation_2pi\(a\d+\[v1\], 'raman_80'\)", src)
    assert set(ctx._shot_arrays) == {'d', 'w'}
    np.testing.assert_array_equal(ctx._shot_arrays['d'], table)

    def bad(fn, exc, match):
        @opx_sequence('_c_sa_bad', claims=('raman',))
        def s_bad(ctx):
            fn(ctx)
        with pytest.raises(exc, match=match):
            _trace(s_bad)

    bad(lambda c: c.shot_array('a', np.zeros((2, 2))), ValueError, 'rows')
    bad(lambda c: c.shot_array('a', np.zeros((3, 2, 2))), ValueError, 'shape')
    bad(lambda c: c.shot_array('a', [0., np.nan, 1.]), ValueError, 'NaN')
    bad(lambda c: c.shot_array('a', [0., 1.5, 1.], dtype=int), ValueError,
        'integral')
    bad(lambda c: c.shot_array('a', [0., 2. ** 31, 1.], dtype=int), ValueError,
        '32-bit')
    bad(lambda c: c.shot_array('a', [0., 8., 1.]), ValueError, 'fixed-point')


def test_host_data_container_filled():
    table = np.arange(6.).reshape(3, 2) * 1.e-6

    @opx_sequence('_c_hd', claims=('raman',), host_data={'h': (2,), 'k': 1})
    def s(ctx):
        ctx.host_data('h', table)
        ctx.host_data('k', np.arange(3))         # (n_shots,) for shape (1,)
        ctx.raman_pulse(ctx.p.t_fixed)

    _ex, _t, b, prog, ctx = _trace(s)
    assert b.host_data == {'h': Stream((2,)), 'k': Stream((1,))}
    np.testing.assert_array_equal(ctx._host_data_values['h'], table)
    assert ctx._host_data_values['k'].shape == (3, 1)

    stub = _stub_with(3, {'h': ((2,), np.float64), 'k': ((1,), np.float64)})
    OPXManager.fill_containers(stub, s, make_map(), {}, {}, {}, 3, specs={},
                               host_data=ctx._host_data_values)
    np.testing.assert_array_equal(stub.data.h._run_data, table)
    np.testing.assert_array_equal(stub.data.k._run_data, [0., 1., 2.])
    assert stub.data.h._data_gotten and stub.data.k._data_gotten

    @opx_sequence('_c_hd_missing', claims=('raman',), host_data={'h': (2,)})
    def s_m(ctx):
        ctx.raman_pulse(ctx.p.t_fixed)
    with pytest.raises(RuntimeError, match='never wrote'):
        _trace(s_m)

    @opx_sequence('_c_hd_shape', claims=('raman',), host_data={'h': (2,)})
    def s_s(ctx):
        ctx.host_data('h', np.zeros((3, 3)))
    with pytest.raises(ValueError, match='expected shape'):
        _trace(s_s)

    @opx_sequence('_c_hd_undecl', claims=('raman',))
    def s_u(ctx):
        ctx.host_data('h', np.zeros((3, 2)))
    with pytest.raises(RuntimeError, match='not declared'):
        _trace(s_u)


# ---------------------------------------------------------------------------
# frequency offsets, aligns, waits
# ---------------------------------------------------------------------------

def test_set_transition_offset_linear():
    @opx_sequence('_c_off', claims=('raman',))
    def s(ctx):
        ctx.set_transition_offset('raman', 1000.)                 # number
        ctx.set_transition_offset('raman', ctx.p.t_raman_pulse * 1.e9)  # per shot
        off = ctx.qua.declare(int, value=1000)
        ctx.set_transition_offset('raman', off)                    # QUA
        ctx.raman_pulse(ctx.p.t_fixed)

    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6, 2.e-6])])
    tables = build_shot_tables(ex)
    b = OPXProgramBuilder(s, make_transition_map(ex), tables, tables.n_shots)
    prog, ctx = b.trace()
    recs = [r for r in b.log.records if r.kind == 'update_frequency'
            and r.macro == 'set_transition_offset']
    assert len(recs) == 6
    f150, f80 = ex.raman.ao_frequencies(F_TR + 1000.)
    by_el = {r.element: r for r in recs[:2]}
    assert by_el['raman_150'].extra['frequency_hz'][0] == hz_to_int(f150)
    assert by_el['raman_80'].extra['frequency_hz'][0] == hz_to_int(f80)
    # the slope is the numeric derivative of the same split
    for el, col in (('raman_150', 0), ('raman_80', 1)):
        d = (np.array(ex.raman.ao_frequencies(F_TR + 1.e3))[col]
             - np.array(ex.raman.ao_frequencies(F_TR - 1.e3))[col]) / 2.e3
        assert by_el[el].extra['slope'] == pytest.approx(float(d), rel=1e-12)
        assert by_el[el].extra['if0_hz'] == hz_to_int(
            np.array(ex.raman.ao_frequencies(F_TR))[col])
    # per-shot host offset: exact split per shot
    col = tables.column('t_raman_pulse') * 1.e9
    a150, a80 = ex.raman.ao_frequencies(F_TR + col)
    by_el2 = {r.element: r for r in recs[2:4]}
    np.testing.assert_array_equal(by_el2['raman_150'].extra['frequency_hz'],
                                  hz_to_int(a150))
    np.testing.assert_array_equal(by_el2['raman_80'].extra['frequency_hz'],
                                  hz_to_int(a80))
    # QUA offset: IF0 + Cast.mul_int_by_fixed(df, slope)
    src = _qua(prog)
    if0_150 = by_el['raman_150'].extra['if0_hz']
    assert re.search(r"update_frequency\('raman_150', \(%d\+Cast\."
                     r"mul_int_by_fixed\(v\d+,[-0-9.e]+\)\), 'Hz', False\)"
                     % if0_150, src)
    assert 'raman' in ctx._if_touched
    i_hb = src.index("'artiq_handback'")
    assert src.index(f"update_frequency('raman_150', {if0_150}, 'Hz', False)",
                     i_hb) > i_hb                                # restored

    @opx_sequence('_c_off_var', claims=('raman',))
    def s_v(ctx):
        ctx.set_transition_offset('raman', 10.)
    ex2 = FakeExpt([('frequency_raman_transition', [F_TR, F_TR + 1.e3])])
    t2 = build_shot_tables(ex2)
    with pytest.raises(RuntimeError, match='varies per shot'):
        OPXProgramBuilder(s_v, make_transition_map(ex2), t2, t2.n_shots).trace()

    def nonlinear(f):
        f = np.asarray(f, dtype=float)
        return {'raman_80': 0.25 * f + 1.e-9 * f ** 2, 'raman_150': 0.75 * f}
    cmap = make_transition_map(ex)
    cmap.channels['raman'].transition_to_ifs = nonlinear
    with pytest.raises(RuntimeError, match='not linear'):
        OPXProgramBuilder(s_v, cmap, tables, tables.n_shots).trace()

    cmap = make_transition_map(ex)
    cmap.channels['raman'].transition_to_ifs = lambda f: {
        'raman_80': 10. * np.asarray(f, float), 'raman_150': 0.5 * np.asarray(f, float)}
    with pytest.raises(RuntimeError, match='fixed'):
        OPXProgramBuilder(s_v, cmap, tables, tables.n_shots).trace()

    @opx_sequence('_c_off_nosplit', claims=('imaging',))
    def s_n(ctx):
        ctx.set_transition_offset('imaging', 10.)
    with pytest.raises(RuntimeError, match='no transition_to_ifs'):
        _trace(s_n)


def test_align_wait_cc_and_elements():
    @opx_sequence('_c_align', claims=('raman', 'imaging'))
    def s(ctx):
        assert ctx.elements('imaging') == dict(switch='imaging_switch',
                                               analog=(), measure='apd')
        assert ctx.elements('raman')['analog'] == ('raman_80', 'raman_150')
        ctx.align('raman', 'imaging')
        ctx.align('raman_80', 'apd')
        ctx.align()
        ctx.wait_cc(2500, 'imaging', 'apd')
        v = ctx.qua.declare(int, value=100)
        ctx.wait_cc(v, 'raman')
        ctx.wait_cc(0, 'raman')                        # nothing emitted
        with pytest.raises(ValueError, match='minimum'):
            ctx.wait_cc(3, 'raman')
        with pytest.raises(TypeError):
            ctx.wait_cc(2500)
        with pytest.raises(KeyError, match='neither'):
            ctx.align('nope')
        with pytest.raises(ValueError):
            ctx.wait_cc(-4, 'raman')

    _ex, _t, b, prog, ctx = _trace(s)
    st = _stmts(_qua(prog))
    i = st.index("align('raman_switch', 'imaging_switch')")
    assert st[i + 1:i + 5] == ["align('raman_80', 'apd')", "align()",
                               "wait(2500, 'imaging_switch', 'apd')",
                               "wait(v2, 'raman_switch')"]
    waits = [r for r in b.log.records if r.macro == 'wait_cc']
    assert waits[0].extra['elements'] == ['imaging_switch', 'apd']
    assert waits[-1].duration_on(0) == 0 and not waits[-1].executes_on(0)
    aligns = [r for r in b.log.records if r.macro == 'align']
    assert [r.extra.get('elements') for r in aligns] == [
        ['raman_switch', 'imaging_switch'], ['raman_80', 'apd'], None]


def test_wait_s_one_align_guard_and_all_elements():
    @opx_sequence('_c_wait', claims=('raman', 'imaging'))
    def s(ctx):
        ctx.wait_s(3.e-6)                       # constant
        ctx.imaging_pulse(ctx.p.t_fixed)        # must follow the wait
        ctx.wait_s(ctx.p.t_raman_pulse)         # 0 on shot 0 -> guarded
        ctx.wait_s(0.)                          # nothing
        v = ctx.qua.declare(int, value=750)
        ctx.wait_s(v)                           # QUA cc -> guarded

    _ex, _t, b, prog, ctx = _trace(s)
    st = _stmts(_qua(prog))
    every = "'raman_switch', 'raman_80', 'raman_150', 'imaging_switch', 'apd', 'artiq_handback'"
    i = st.index(f"wait(750, {every})")
    assert st[i - 1] == "align()"
    assert st[i + 1] == "play('pass', 'imaging_switch', duration=1250)"
    j = st.index("with if_((a1[v1]>=4)):")
    assert st[j - 1] == "align()" and st[j + 1] == f"wait(a1[v1], {every})"
    k = st.index("with if_((v2>=4)):")
    assert st[k - 1] == "align()" and st[k + 1] == f"wait(v2, {every})"
    # zero constant wait: one align, no wait statement, a skipped record
    body = [r for r in b.log.records if r.macro == 'wait_s']
    zero = [r for r in body if r.kind == 'wait' and r.executes is not None
            and not r.executes.any()]
    assert len(zero) == 1
    assert body[0].kind == 'align'
    assert [r.kind for r in body].count('align') == 4


# ---------------------------------------------------------------------------
# builder framing
# ---------------------------------------------------------------------------

def test_builder_framing_echo_settle_and_streams():
    @opx_sequence('_c_frame', claims=('raman', 'imaging'),
                  measurements={'lw': Stream((2, 3)), 'sig': 1})
    def s(ctx):
        w = ctx.qua.declare(ctx.qua.fixed, value=0.5)
        ctx.measure('sig')
        with ctx.for_range(2):
            with ctx.for_range(3):
                ctx.save('lw', w)

    _ex, _t, b, prog, ctx = _trace(s)
    src = _qua(prog)
    st = _stmts(src)
    i = st.index("wait_for_trigger('raman_switch')")
    assert st[i + 1:i + 7] == [
        "save(v1, r1)", "align()", "play('block', 'raman_switch')",
        "play('block', 'imaging_switch')",
        "wait(2500, 'raman_switch', 'imaging_switch')", "align()"]
    assert 'r1.save_all("opx_shot_index")' in src
    assert re.search(r"r\d+\.buffer\(3\)\.buffer\(2\)\.save_all\(\"lw\"\)", src)
    from kexp.control.opx.builder import RESERVED_STREAMS
    assert b.stream_specs() == {'lw': Stream((2, 3)), 'sig': Stream((1,)),
                                **RESERVED_STREAMS}
    echo = [r for r in b.log.records if r.data_key == SHOT_INDEX_KEY]
    assert len(echo) == 1 and echo[0].kind == 'save'
    assert echo[0].phase == 'handshake' and echo[0].source is None
    # no A5 without a drive re-point; A5 + restore with one
    assert src.count('align()') == 4

    @opx_sequence('_c_frame_a5', claims=('raman',))
    def s5(ctx):
        ctx.set_transition('raman', ctx.p.frequency_raman_transition + 5.e3)
    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6])])
    tables = build_shot_tables(ex)
    prog5, _ = OPXProgramBuilder(s5, make_transition_map(ex), tables,
                                 tables.n_shots).trace()
    src5 = _qua(prog5)
    assert src5.count('align()') == 5
    st5 = _stmts(src5)
    k = st5.index("play('pass', 'imaging_switch')")
    assert st5[k + 1] == "align()" and st5[k + 2].startswith(
        "update_frequency('raman_80'")


def test_viewer_line_map_survives_new_statement_kinds():
    # the pulse viewer maps op-log records onto the serialized QUA text
    # one-to-one; loops, timestamped plays, the else_ placeholder save, the
    # echo save and named aligns must keep that mapping intact, and the
    # execution expander must not choke on the opaque 'for' records
    from kexp.control.opx.viewer import qua_line_map, expand_execution
    from qm import generate_qua_script

    @opx_sequence('_c_viewer', claims=('raman', 'imaging'),
                  measurements={'sig': 2, 't_p': Stream(2, int),
                                'lw': Stream((2, 3))})
    def s(ctx):
        w = ctx.qua.declare(ctx.qua.fixed, value=0.5)
        d = ctx.shot_array('d', np.tile([0, 500], (ctx.n_shots, 1)), dtype=int)
        with ctx.for_range(2) as i:
            ctx.raman_pulse(d.at(i), phase_reset=True, timestamp_key='t_p')
            ctx.measure('sig')
            ctx.wait_cc(250, 'raman')
            with ctx.for_range(3):
                ctx.save('lw', w)
        ctx.align('raman', 'imaging')
        ctx.wait_s(ctx.p.t_raman_pulse)

    _ex, _t, b, prog, ctx = _trace(s)
    qmap, err = qua_line_map(b.log, generate_qua_script(prog))
    assert err == '' and qmap
    mapped = [r for r in b.log.records if r.kind not in ('for', 'assign')]
    assert all(r.index in qmap for r in mapped)
    assert not any(r.index in qmap for r in b.log.records if r.kind == 'for')
    items = expand_execution(b.log, 3)
    assert any(r.kind == 'for' for r, _s in items)
    assert not any(r.kind == 'if' for r, _s in items)


# ---------------------------------------------------------------------------
# manager: config-time guard, use(), provenance
# ---------------------------------------------------------------------------

def test_config_time_param_as_xvar_refused(monkeypatch):
    with pytest.raises(RuntimeError, match='t_imaging_pulse_apd_abs'):
        check_config_time_xvars(
            SimpleNamespace(xvarnames=['t_imaging_pulse_apd_abs', 't_tof']),
            ('t_imaging_pulse_apd_abs', 't_opx_integration_len'))
    check_config_time_xvars(SimpleNamespace(xvarnames=['t_tof']),
                            ('t_imaging_pulse_apd_abs',))
    check_config_time_xvars(SimpleNamespace(xvarnames=['t_tof']), ())

    @opx_sequence('_c_cfg', claims=('raman',))
    def s(ctx):
        ctx.raman_pulse(ctx.p.t_raman_pulse)

    # scanned before use(): refused at use(), before anything is registered
    stub = ManagerStub([('t_fixed', [5.e-6, 6.e-6])])
    cmap = make_map()
    cmap.config_time_params = ('t_fixed',)
    m = _manager(stub, cmap, monkeypatch=monkeypatch)
    with pytest.raises(RuntimeError, match="'t_fixed'"):
        m.use(s)
    assert not m.active and not hasattr(stub.data, VALID_MASK_KEY)

    # scanned after use(): refused at finish_prepare (before the trace)
    stub = ManagerStub([('t_raman_pulse', [0., 1.e-6])])
    m = _manager(stub, cmap, monkeypatch=monkeypatch)
    m.use(s)
    stub.scan_xvars.append(SimpleNamespace(key='t_fixed',
                                           values=np.array([5.e-6, 6.e-6])))
    stub.xvarnames.append('t_fixed')
    stub.xvardims = [2, 2]
    with pytest.raises(RuntimeError, match="'t_fixed'"):
        m.on_finish_prepare()

    # an adjust() on a config-time key: covered by the accessed set
    stub = ManagerStub([('t_raman_pulse', [0., 1.e-6])])
    stub._adjust_specs = [SimpleNamespace(key='t_fixed')]
    m = _manager(stub, cmap, monkeypatch=monkeypatch)
    m.use(s)
    with pytest.raises(RuntimeError, match='registered with adjust'):
        m.on_finish_prepare()


def test_use_registers_containers_and_checks_shapes(monkeypatch):
    @opx_sequence('_c_use', claims=('raman', 'imaging'),
                  measurements={'sig': lambda p: p.N_pulses,
                                'lw': lambda p: Stream((p.N_pulses, 3)),
                                'ts': Stream(2, int)},
                  host_data={'h': (2,)})
    def s(ctx):
        pass

    stub = ManagerStub([('t_raman_pulse', [0., 1.e-6])])
    stub.params.N_pulses = 2
    m = _manager(stub, monkeypatch=monkeypatch)
    m.use(s)
    d = stub.data
    assert d.sig._per_shot_data_shape == (2,) and d.sig._dtype is np.float64
    assert d.lw._per_shot_data_shape == (2, 3)
    assert d.ts._per_shot_data_shape == (2,) and d.ts._dtype is np.int64
    assert d.h._per_shot_data_shape == (2,) and d.h._dtype is np.float64
    assert getattr(d, VALID_MASK_KEY)._dtype is np.int32
    assert getattr(d, SHOT_INDEX_KEY)._dtype is np.int32
    assert m._measurements == {'sig': Stream((2,)), 'lw': Stream((2, 3)),
                               'ts': Stream((2,), int)}
    with pytest.raises(RuntimeError, match='twice'):
        m.use(s)
    # the shape's parameter moved after use(): refused at finish_prepare
    stub.params.N_pulses = 3
    with pytest.raises(RuntimeError, match='changed between use'):
        m.on_finish_prepare()

    @opx_sequence('_c_use_reserved', claims=(),
                  measurements={SHOT_INDEX_KEY: 1})
    def s_r(ctx):
        pass
    stub = ManagerStub([('t_raman_pulse', [0.])])
    with pytest.raises(ValueError, match='reserved'):
        _manager(stub, monkeypatch=monkeypatch).use(s_r)


def test_on_finish_prepare_writes_provenance_texts(monkeypatch):
    from kexp.control.opx.opx_config import build_opx_config

    @opx_sequence('_c_prov', claims=('raman',), host_data={'h': (2,)})
    def s(ctx):
        # sized from ctx.n_shots: the simulate branch re-traces the body on
        # a table sliced to simulate_shots
        table = np.tile([250, 500], (ctx.n_shots, 1))
        d = ctx.shot_array('d', table, dtype=int)
        ctx.host_data('h', table * 4.e-9)
        ctx.raman_pulse(d.at(0))
        ctx.wait_s(ctx.p.t_fixed)

    stub = ManagerStub([('t_raman_pulse', [0., 1.e-6])])
    p = stub.params
    p.t_imaging_pulse_apd_abs = 5.e-6
    p.t_opx_integration_start = 0.
    p.t_opx_integration_len = 5.e-6
    cmap = make_transition_map(stub)
    cmap.machine = SimpleNamespace(to_dict=lambda: {'elements': ['x'],
                                                    '__class__': 'Fake'})
    m = _manager(stub, cmap, config=build_opx_config, monkeypatch=monkeypatch)
    monkeypatch.setattr(OPXManager, '_run_simulation',
                        lambda self, prog, config: None)
    m._exit_after_simulate = False
    m.use(s, simulate=True, simulate_viewer=False, simulate_web_plot=False)
    m.on_finish_prepare()

    texts = stub._extra_file_texts
    assert 'wait_for_trigger' in texts[QUA_SOURCE_ATTR]
    assert json.loads(texts[MACHINE_ATTR]) == {'elements': ['x'],
                                               '__class__': 'Fake'}
    doc = json.loads(texts[SHOT_TABLES_ATTR])
    assert doc['sequence'] == '_c_prov' and doc['n_shots'] == 2
    assert doc['xvardims'] == [2] and doc['xvarnames'] == ['t_raman_pulse']
    assert 't_fixed' in doc['accessed']
    assert 'frequency_raman_transition' in doc['accessed']   # config-time read
    assert doc['columns']['t_fixed'] == [5.e-6, 5.e-6]
    assert set(doc['columns']) == set(doc['accessed'])
    assert doc['shot_arrays'] == {'d': [2, 2]}
    assert doc['host_data'] == {'h': {'shape': [2], 'dtype': 'float'}}
    assert doc['simulate'] is True and doc['host'] == 'none'
    assert doc['qm_version']
    assert m._host_values['h'].shape == (2, 2)


class _FakeLiveODClient:
    def __init__(self):
        self.aborts = 0

    def abort_run(self):
        self.aborts += 1


def test_simulate_exit_aborts_live_od_run(monkeypatch):
    """simulate=True under artiq_run: the run finish_prepare registered with
    liveOD never takes a shot, so ABORT_RUN goes out once the simulation is
    done -- and also when it raises. OPXBench (_exit_after_simulate=False)
    keeps its process and sends nothing."""
    @opx_sequence('_c_sim_abort', claims=())
    def s(ctx):
        ctx.wait_s(1.e-6)

    def ready(exit_after, sim=lambda self, prog, config: None):
        stub = ManagerStub([('t_raman_pulse', [0., 1.e-6])])
        stub.live_od_client = _FakeLiveODClient()
        m = _manager(stub, monkeypatch=monkeypatch)
        monkeypatch.setattr(OPXManager, '_run_simulation', sim)
        m._exit_after_simulate = exit_after
        m.use(s, simulate=True, simulate_viewer=False,
              simulate_web_plot=False)
        return m, stub.live_od_client

    m, client = ready(True)
    with pytest.raises(SystemExit):
        m.on_finish_prepare()
    assert client.aborts == 1

    def boom(self, prog, config):
        raise RuntimeError('simulator down')
    m, client = ready(True, boom)
    with pytest.raises(RuntimeError, match='simulator down'):
        m.on_finish_prepare()
    assert client.aborts == 1

    m, client = ready(False)
    m.on_finish_prepare()
    assert client.aborts == 0


# ---------------------------------------------------------------------------
# manager: fetch / fill / finish
# ---------------------------------------------------------------------------

def test_fill_2d_and_int_containers(capsys):
    stub = _stub_with(4, {'lw': ((2, 3), np.float64), 'ts': ((2,), np.int64),
                          'sig': ((1,), np.float64)})
    seq = OPXSequence(lambda ctx: None, name='_c_fill2d')
    specs = {'lw': Stream((2, 3)), 'ts': Stream(2, int), 'sig': Stream(1),
             SHOT_INDEX_KEY: Stream(1, int)}
    lw = np.arange(18.).reshape(3, 2, 3)
    ts = np.array([[10, 20], [30, 40], [50, 60]], dtype=np.int64)
    sig = np.array([1., 2., 3.])
    fetched = {'lw': lw, 'ts': ts, 'sig': sig,
               SHOT_INDEX_KEY: np.arange(3)}
    counts = {'lw': 3, 'ts': 3, 'sig': 3, SHOT_INDEX_KEY: 3}
    OPXManager.fill_containers(stub, seq, make_map(), {'sig': 'imaging'},
                               fetched, counts, 4, specs=specs)
    d = stub.data
    assert d.lw._run_data.shape == (4, 2, 3)
    np.testing.assert_array_equal(d.lw._run_data[:3], lw)   # raw, no volts
    assert np.all(np.isnan(d.lw._run_data[3]))
    assert d.ts._run_data.dtype == np.int64
    np.testing.assert_array_equal(d.ts._run_data[:3], ts)
    assert list(d.ts._run_data[3]) == [INT_MISSING, INT_MISSING]
    assert d.sig._run_data[0] == pytest.approx(4096. / 5000.)   # volts
    assert np.isnan(d.sig._run_data[3])
    echo = getattr(d, SHOT_INDEX_KEY)._run_data
    assert echo.dtype == np.int32 and list(echo) == [0, 1, 2, INT_MISSING]
    assert list(getattr(d, VALID_MASK_KEY)._run_data) == [1, 1, 1, 0]
    assert all(getattr(d, k)._data_gotten
               for k in ('lw', 'ts', 'sig', SHOT_INDEX_KEY, VALID_MASK_KEY))
    out = capsys.readouterr().out
    assert '3 of 4' in out and 'raw integration' in out


def test_shot_index_echo_mismatch_flags(capsys):
    stub = _stub_with(4, {'sig': ((1,), np.float64)})
    seq = OPXSequence(lambda ctx: None, name='_c_echo')
    specs = {'sig': Stream(1), SHOT_INDEX_KEY: Stream(1, int)}
    fetched = {'sig': np.array([1., 2., 3., 4.]),
               SHOT_INDEX_KEY: np.array([0, 1, 3, 4])}     # shot 2 skipped
    counts = {'sig': 4, SHOT_INDEX_KEY: 4}
    OPXManager.fill_containers(stub, seq, make_map(), {'sig': 'imaging'},
                               fetched, counts, 4, specs=specs)
    assert list(getattr(stub.data, VALID_MASK_KEY)._run_data) == [1, 1, 0, 0]
    # values are kept as fetched, the mask says what to trust
    assert np.all(np.isfinite(stub.data.sig._run_data))
    assert list(getattr(stub.data, SHOT_INDEX_KEY)._run_data) == [0, 1, 3, 4]
    out = capsys.readouterr().out
    assert '***' in out and 'from shot 2' in out and '2 of 4' in out

    # a clean echo keeps every shot
    stub = _stub_with(3, {'sig': ((1,), np.float64)})
    OPXManager.fill_containers(
        stub, seq, make_map(), {'sig': 'imaging'},
        {'sig': np.ones(3), SHOT_INDEX_KEY: np.arange(3)},
        {'sig': 3, SHOT_INDEX_KEY: 3}, 3, specs=specs)
    assert list(getattr(stub.data, VALID_MASK_KEY)._run_data) == [1, 1, 1]
    assert '***' not in capsys.readouterr().out


class _Handle:
    def __init__(self, arr):
        self.arr = np.asarray(arr)

    def count_so_far(self):
        return len(self.arr)

    def fetch_all(self):
        return self.arr


class _Handles:
    def __init__(self, arrays, fail_first=True):
        self.arrays = arrays
        self.fail = fail_first
        self.calls = 0

    def get(self, key):
        self.calls += 1
        if self.fail:
            self.fail = False
            raise RuntimeError("transient fetch failure")
        return _Handle(self.arrays[key])


def test_finish_reentrant_after_failed_fetch():
    stub = _stub_with(3, {'sig': ((1,), np.float64)})
    hook_calls = []
    seq = OPXSequence(lambda ctx: None, name='_c_finish',
                      measurements={'sig': 1},
                      finish=lambda expt, data: hook_calls.append((expt, data)))
    m = OPXManager(stub, host='none', cluster='none',
                   map_builder=lambda e: make_map(),
                   config_builder=lambda e, t: {})
    m._sequence = seq
    m._map = make_map()
    m._n_shots = 3
    m._stream_specs = {'sig': Stream(1), SHOT_INDEX_KEY: Stream(1, int)}
    m._stream_roles = {'sig': 'imaging'}
    halted = []
    handles = _Handles({'sig': np.array([1., 2., 3.]),
                        SHOT_INDEX_KEY: np.arange(3)})
    job = SimpleNamespace(result_handles=handles,
                          halt=lambda: halted.append(1))
    m._job = job

    with pytest.raises(RuntimeError, match='transient'):
        m.finish(timeout=0.)
    assert not m._finished and m._job is job and not halted
    assert not stub.data.sig._data_gotten and hook_calls == []

    m.finish(timeout=0.)
    assert m._finished and halted == [1] and m._job is None
    assert stub.data.sig._data_gotten
    assert stub.data.sig._run_data[1] == pytest.approx(4096. * 2. / 5000.)
    assert list(getattr(stub.data, VALID_MASK_KEY)._run_data) == [1, 1, 1]
    assert hook_calls == [(stub, stub.data)]
    m.finish()                       # idempotent now
    assert halted == [1] and handles.calls == 3

    # a failing hook: the raw containers are filled and the job halted,
    # the error reaches the caller
    stub = _stub_with(2, {'sig': ((1,), np.float64)})
    seq = OPXSequence(lambda ctx: None, name='_c_finish_hook',
                      measurements={'sig': 1},
                      finish=lambda expt, data: 1 / 0)
    m._expt, m._sequence, m._n_shots, m._finished = stub, seq, 2, False
    halted.clear()
    m._job = SimpleNamespace(
        result_handles=_Handles({'sig': np.array([1., 2.]),
                                 SHOT_INDEX_KEY: np.arange(2)}, False),
        halt=lambda: halted.append(1))
    with pytest.raises(ZeroDivisionError):
        m.finish(timeout=0.)
    assert m._finished and halted == [1] and stub.data.sig._data_gotten


def test_min_cc_skips_the_guard_on_qua_durations():
    # a host-asserted lower bound on a QUA-expression duration removes the
    # per-shot if_ so a phase-reset pulse has no run-time branch in front
    table = np.array([[900, 1200], [1000, 1100], [1100, 1000]])

    @opx_sequence('_c_mincc', claims=('raman',))
    def s(ctx):
        d = ctx.shot_array('d', table, dtype=int)
        with ctx.for_range(2) as i:
            ctx.raman_pulse(d.at(i), phase_reset=True,
                            min_cc=int(table.min()))
        ctx.raman_pulse(d.at(0))                       # no bound: guarded

    _ex, _t, b, prog, _ctx = _trace(s)
    st = _stmts(_qua(prog))
    i = st.index("reset_if_phase('raman_80')")
    assert st[i - 1].startswith("with for_(")          # loop head, no if_
    assert st[i + 2] == "align('raman_80', 'raman_150', 'raman_switch')"
    assert st[i + 3].startswith("play('pass', 'raman_switch', duration=a")
    assert any(x.startswith("with if_(") for x in st)  # the unbounded one
    kinds = [r.kind for r in b.log.records if r.macro == 'raman_pulse']
    assert kinds[:5] == ['reset_if_phase', 'reset_if_phase', 'align',
                         'play', 'play']

    @opx_sequence('_c_mincc_bad', claims=('raman',))
    def s_bad(ctx):
        d = ctx.shot_array('d', table, dtype=int)
        ctx.raman_pulse(d.at(0), min_cc=2)
    with pytest.raises(ValueError, match='below the 4-cycle minimum'):
        _trace(s_bad)


def test_expose_timestamp_key_on_measure():
    # a measure can timestamp its exposure play (an int stream, one save);
    # the builder's framing plays carry no timestamps
    @opx_sequence('_c_tsexp', claims=('raman', 'imaging'),
                  measurements={'sig': 1, 'texp': Stream(1, int),
                                'tmeas': Stream(1, int)})
    def s(ctx):
        ctx.measure('sig', timestamp_key='tmeas', expose_timestamp_key='texp')

    _ex, _t, b, prog, ctx = _trace(s)
    st = _stmts(_qua(prog))
    exp = [x for x in st if x.startswith("play('pass', 'imaging_switch'")
           and 'duration=' in x]                 # the exposure, not the release
    assert len(exp) == 1 and 'timestamp_stream=' in exp[0]
    hb = [x for x in st if "'artiq_handback'" in x and x.startswith('play(')]
    assert hb == ["play('trigger', 'artiq_handback')"]
    blk = [x for x in st if x.startswith("play('block', 'raman_switch'")]
    assert all('timestamp_stream' not in x for x in blk)
    assert ctx._save_counts['texp'] == 1 and ctx._save_counts['tmeas'] == 1
    assert set(b.stream_specs()) == {'sig', 'texp', 'tmeas', SHOT_INDEX_KEY}

    @opx_sequence('_c_tsexp_bad', claims=('imaging',),
                  measurements={'sig': 1, 'texp': Stream(1, int)})
    def s_bad(ctx):
        ctx.measure('sig', expose=False, expose_timestamp_key='texp')
    with pytest.raises(RuntimeError, match='plays no exposure'):
        _trace(s_bad)


def test_transition_offset_terms_match_set_transition_offset():
    seq_terms = {}

    @opx_sequence('_c_terms', claims=('raman',))
    def s(ctx):
        seq_terms.update(ctx.transition_offset_terms('raman'))
        ctx.raman_pulse(ctx.p.t_fixed)

    ex = FakeExpt([('t_raman_pulse', [0., 1.e-6])])
    tables = build_shot_tables(ex)
    cmap = make_transition_map(ex)
    OPXProgramBuilder(s, cmap, tables, tables.n_shots).trace()
    f150, f80 = ex.raman.ao_frequencies(F_TR)
    assert seq_terms['raman_150'][0] == hz_to_int(f150)
    assert seq_terms['raman_80'][0] == hz_to_int(f80)
    # a two-photon offset df moves (f150 - f80) by df/2 (double pass):
    # slope_150 - slope_80 == 1/2
    assert abs(seq_terms['raman_150'][1] - seq_terms['raman_80'][1] - 0.5) < 1e-9
