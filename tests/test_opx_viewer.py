"""Offline tests for the OPX pulse viewer adapter (kexp.control.opx.viewer):
op-log provenance, report matching against the offline simulator fixture,
truncation and mismatch warnings, QUA line mapping, bundle round trip.

Run from the workspace root with the root venv:
    .venv/Scripts/python.exe -m pytest k-exp/tests/test_opx_viewer.py
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_opx import FakeExpt, make_map                       # noqa: E402
from opx_sim_fixture import simulate_job, fake_config         # noqa: E402

from kexp.control.opx.params_bridge import build_shot_tables  # noqa: E402
from kexp.control.opx.builder import OPXProgramBuilder        # noqa: E402
from kexp.control.opx.sequence import opx_sequence            # noqa: E402
from kexp.control.opx.trace_log import PHASE_BODY, PHASE_HANDSHAKE  # noqa: E402
from kexp.control.opx.viewer import (build_bundle, expand_execution,  # noqa: E402
                                     qua_line_map, fmt_ns)
from waxx.util.seqview.bundle import Bundle                   # noqa: E402


@opx_sequence('viewer_probe', claims=('raman', 'imaging'),
              measurements={'apd_qm': 2})
def viewer_probe(ctx):
    ctx.raman_phase_reset()
    ctx.raman_pulse(ctx.p.t_raman_pulse)
    ctx.wait_s(3.e-6)
    ctx.set_frequency('raman', 81.e6, which=0)
    ctx.measure('apd_qm')
    ctx.wait_s(2.e-6)
    ctx.measure('apd_qm', expose=False)


def _trace(seq, xvals, n_shots=None, cmap=None, params=None):
    ex = FakeExpt([('t_raman_pulse', list(xvals))])
    for key, value in (params or {}).items():
        setattr(ex.params, key, value)
    tables = build_shot_tables(ex)
    cmap = cmap if cmap is not None else make_map()
    b = OPXProgramBuilder(seq, cmap, tables, tables.n_shots)
    prog, ctx = b.trace(skip_triggers=True)
    return b, prog, ctx


def _bundle(seq, xvals, duration_ns, qua=True, cmap=None, params=None):
    cmap = cmap if cmap is not None else make_map()
    b, prog, ctx = _trace(seq, xvals, cmap=cmap, params=params)
    cfg = fake_config()
    qua_sim = ''
    if qua:
        from qm import generate_qua_script
        qua_sim = generate_qua_script(prog)
    job = simulate_job(b.log, cfg, b.n_shots, duration_ns, program=prog, ctx=ctx)
    return build_bundle(job, b, cmap, cfg, duration_ns, qua_sim=qua_sim,
                        info={'title': 'test'}), b, job


# ---------------------------------------------------------------------------
# op log provenance
# ---------------------------------------------------------------------------

def test_op_log_source_lines_and_phases():
    b, prog, ctx = _trace(viewer_probe, [0., 4.e-6])
    log = b.log
    body = [r for r in log.records if r.phase == PHASE_BODY]
    assert body, "body records missing"
    # every body record points into this file, at the line of its macro call
    lines = {}
    for r in body:
        assert r.source is not None and r.source.file == __file__
        lines.setdefault(r.macro, set()).add(r.source.line)
    src = open(__file__, encoding='utf-8').read().splitlines()
    for macro, ls in lines.items():
        for ln in ls:
            assert macro.split('_')[0] in src[ln - 1] or macro in src[ln - 1], \
                (macro, ln, src[ln - 1])
    # framing records carry no source line
    for r in log.records:
        if r.phase == PHASE_HANDSHAKE:
            assert r.source is None
    # the per-shot if guard and its plays know which shots they run on
    pulse = next(r for r in body if r.macro == 'raman_pulse' and r.op == 'pass')
    assert list(pulse.executes) == [False, True]
    assert list(pulse.duration_cc) == [0, 1000]
    assert pulse.label == 't_raman_pulse'
    # macro call groups
    calls = {r.call for r in body}
    assert len(calls) == 7   # phase_reset, pulse, wait, set_frequency, measure, wait, measure


def test_expand_execution_skips_guarded_shots():
    b, *_ = _trace(viewer_probe, [0., 4.e-6])
    items = expand_execution(b.log, 2)
    shot0 = [r for r, s in items if s == 0 and r.macro == 'raman_pulse']
    shot1 = [r for r, s in items if s == 1 and r.macro == 'raman_pulse']
    assert shot0 == []
    assert [r.op for r in shot1] == ['pass', 'block']
    assert not any(r.kind == 'if' for r, s in items)


def test_qua_line_map_is_one_to_one():
    b, prog, ctx = _trace(viewer_probe, [0., 4.e-6])
    from qm import generate_qua_script
    text = generate_qua_script(prog)
    qmap, err = qua_line_map(b.log, text)
    assert err == ''
    lines = text.splitlines()
    for r in b.log.records:
        if r.kind in ('play', 'wait', 'measure', 'update_frequency', 'reset_if_phase'):
            assert r.index in qmap
            stmt = lines[qmap[r.index] - 1].strip()
            head = {'play': 'play(', 'wait': 'wait(', 'measure': 'measure(',
                    'update_frequency': 'update_frequency(',
                    'reset_if_phase': 'reset_if_phase('}[r.kind]
            assert stmt.startswith(head), (r, stmt)
    bogus = chr(10).join(["with program() as p:", "    play('x', 'y')", ""])
    bad, err = qua_line_map(b.log, bogus)
    assert bad == {} and 'line mapping disabled' in err


# ---------------------------------------------------------------------------
# bundle building
# ---------------------------------------------------------------------------

def test_bundle_complete_window_has_no_warnings():
    bundle, b, job = _bundle(viewer_probe, [0., 4.e-6], 400_000)
    m = bundle.meta
    levels = [w['level'] for w in m['warnings']]
    assert 'error' not in levels, m['warnings']
    assert len(m['shots']) == 2
    ids = {ln['id'] for ln in m['lanes']}
    assert {'steps', 'light:raman', 'light:imaging', 'adc:imaging', 'handback',
            'D1', 'D2', 'D3', 'D4', 'A1', 'A2'} <= ids
    # shot 0 has no raman exposure (t = 0), shot 1 has one of 4 us
    exp = [p for p in m['pulses'] if p['lane'] == 'light:raman']
    assert [p['shot'] for p in exp] == [1]
    assert exp[0]['t1'] - exp[0]['t0'] == pytest.approx(4000.)
    assert exp[0]['value_str'].startswith('t_raman_pulse = 4')
    assert exp[0]['src_line'] and exp[0]['qua_line']
    # ADC windows: 2 per shot, the dark one flagged in its text
    adc = [p for p in m['pulses'] if p['lane'] == 'adc:imaging']
    assert len(adc) == 4
    assert sum('dark' in p['text'] for p in adc) == 2
    # framing bands per shot
    kinds = sorted((f['shot'], f['kind']) for f in m['framing'])
    assert kinds == [(0, 'handback'), (0, 'handoff'), (1, 'handback'), (1, 'handoff')]
    # events: phase resets (reported) and the IF change (inferred)
    kinds = sorted(e['kind'] for e in m['events'])
    assert kinds == ['reset_if_phase', 'reset_if_phase', 'reset_if_phase',
                     'reset_if_phase', 'update_frequency', 'update_frequency']
    assert all(not e['approx'] for e in m['events'] if e['kind'] == 'reset_if_phase')
    assert all(e['approx'] for e in m['events'] if e['kind'] == 'update_frequency')
    assert 'IF' in next(e['label'] for e in m['events'] if e['kind'] == 'update_frequency')
    # params table lists only what the sequence read
    assert m['params']['names'] == ['t_raman_pulse']
    # steps lane: one bar per macro call per shot, handshake bars grey
    steps = [p for p in m['pulses'] if p['lane'] == 'steps']
    macros = [p['macro'] for p in steps if p['shot'] == 1]
    assert macros[:2] == ['handoff', 'raman_phase_reset'] or macros[0] == 'handoff'
    assert 'handback' in macros and 'wait_s' in macros and 'measure' in macros
    # a step bar spans its group: the measure bar reaches the ADC window end
    meas = next(p for p in steps if p['macro'] == 'measure' and p['shot'] == 0)
    adc0 = next(p for p in adc if p['shot'] == 0)
    assert meas['t1'] == pytest.approx(adc0['t1'])
    # digital edge arrays match the exposure edges (cross-check passes)
    e1 = bundle.array(bundle.lane('D1')['edges'])
    assert np.any(np.abs(e1 - exp[0]['t0']) < 1.5) and np.any(np.abs(e1 - exp[0]['t1']) < 1.5)


def test_bundle_analog_lanes_show_the_latched_amplitude():
    # a map with a power_fraction_param latches at amp(sqrt(f)): the analog
    # lanes label the latched volts, and the simulated tone carries them
    import dataclasses
    cmap = make_map()
    cmap.channels['raman'] = dataclasses.replace(
        cmap.channels['raman'], power_fraction_param='fraction_power_raman')
    bundle, b, job = _bundle(viewer_probe, [0., 4.e-6], 400_000, cmap=cmap,
                             params={'fraction_power_raman': 0.36})
    notes = {ln['id']: ln['note'] for ln in bundle.meta['lanes']}
    # fake_config: 0.25 V (raman_80, A1) and 0.3 V (raman_150, A2)
    assert '0.15 V (config 0.25 V x amp 0.6)' in notes['A1']
    assert '0.18 V (config 0.3 V x amp 0.6)' in notes['A2']
    assert 'fraction_power_raman' in bundle.meta['params']['names']
    a1 = np.asarray(job.get_simulated_samples().con1.analog['1'], dtype=float)
    win = a1[5_000:25_000]
    assert np.sqrt(2) * float(np.sqrt(np.mean(np.square(win)))) == \
        pytest.approx(0.15, rel=1e-3)


def test_bundle_truncation_is_flagged():
    bundle, b, job = _bundle(viewer_probe, [0., 4.e-6], 20_000)
    m = bundle.meta
    errs = [w['text'] for w in m['warnings'] if w['level'] == 'error']
    assert any('ended before the program' in t for t in errs), m['warnings']
    assert any(f['kind'] == 'not_simulated' for f in m['framing'])
    red = [p for p in m['pulses'] if p['color'] == '#ff5555']
    assert red, "unsimulated pulses should be marked"
    assert all('NOT SIMULATED' in p['note'] for p in red)


def test_bundle_round_trip(tmp_path):
    bundle, b, job = _bundle(viewer_probe, [4.e-6], 200_000, qua=False)
    path = tmp_path / 'b.npz'
    bundle.save(path)
    back = Bundle.load(path)
    assert back.meta['pulses'] == bundle.meta['pulses']
    assert set(back.arrays) == set(bundle.arrays)
    for k in bundle.arrays:
        assert np.array_equal(back.arrays[k], bundle.arrays[k])
    assert 'qua' not in back.meta['sources']
    assert any(w['level'] == 'info' for w in back.meta['warnings'])   # no QUA text


def test_report_program_disagreement_is_an_error():
    bundle, b, job = _bundle(viewer_probe, [4.e-6], 200_000, qua=False)
    rep = job.get_simulated_waveform_report()
    # corrupt the report: drop the first raman_switch waveform
    import dataclasses
    keep = [w for w in rep.digital_waveforms if w.element != 'raman_switch']
    bad = dataclasses.replace(rep, digital_waveforms=keep)

    class Job:
        def get_simulated_samples(self):
            return job.get_simulated_samples()

        def get_simulated_waveform_report(self):
            return bad

    from kexp.control.opx.viewer import build_bundle as bb
    out = bb(Job(), b, make_map(), fake_config(), 200_000)
    errs = [w['text'] for w in out.meta['warnings'] if w['level'] == 'error']
    assert any('not reported by the simulator' in t for t in errs), errs


def test_fmt_ns():
    assert fmt_ns(16) == '16 ns'
    assert fmt_ns(3000) == '3 µs'
    assert fmt_ns(2.5e6) == '2.5 ms'
