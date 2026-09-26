"""Offline stand-in for the Quantum Machines QOP simulator.

Lets the OPX pulse viewer (and anything else that consumes
``job.get_simulated_samples()`` / ``job.get_simulated_waveform_report()``)
be exercised without a QOP on the network. Nothing here opens a socket: the
"simulation" is a small deterministic scheduler that replays the builder's
OpLog (kexp.control.opx.trace_log) against a QUA config dict and constructs
the REAL qm result classes directly (qm 1.4.1: PlayedAnalogWaveform,
PlayedDigitalWaveform, AdcAcquisition, Event, WaveformReport,
SimulatorSamples, SimulatorControllerSamples), so the consumer sees the exact
types it gets from a real simulate().

Public API
----------
simulate_offline(log, config, n_shots, duration_ns, skip_triggers=True)
    -> (samples, report)
OfflineJob(samples, report, ...)       duck-types qm's SimulatedJob
trace_and_simulate(sequence, xvars, duration_ns, n_shots=None,
                   skip_triggers=True) -> OfflineJob
fake_config(a_80=0.25, a_150=0.3)      the K-machine QUA config (real builder)
predicted_digital_plays(log, config, n_shots, port) -> int

THIS IS NOT THE QOP. Simplifications (deliberate, keep them in mind when a
viewer result looks "right" here but not on the real simulator):

* Every element has its own clock; ops run back-to-back on it. No compiler
  gaps, no pipeline latency, no minimum-length padding, digitalInputs
  delay/buffer and analog output delays are ignored.
* EVERY align is treated as a global align (all config elements jump to the
  latest clock). The log does not record which elements a two-element
  align (ctx.measure's align(switch, apd)) named; in the sequences traced
  so far that align always directly follows a global one, so it is
  equivalent there.
* Sticky analog: a play (re)latches the element's tone from its start --
  amplitudes do NOT accumulate the way repeated sticky plays do on the OPX.
  The builder only latches once per run, so this does not arise in practice.
  The tone is amp*sin(2*pi*f*(t - t_origin)*1e-9 + phase) with t_origin = 0
  (or the last reset_if_phase); the real OPX outputs a cosine. Only
  constant waveforms are supported.
* update_frequency / frame_rotation_2pi / reset_frame / reset_if_phase
  change the synthesized tone but have no time cost; only reset_if_phase
  produces a report entry (Event 'phase_reset', like the real report).
* ramp_to_zero is a linear ramp over the element's sticky 'duration'.
* Sticky digital: during the play the line follows the digital marker; after
  it the marker's last level is held until the next play on that element.
  Non-sticky digital: the line follows the marker for exactly the pulse
  length. Several elements on one port are OR'ed (analog: summed).
* skip_triggers=True: wait_for_trigger records are ignored (they are not in
  a log traced with skip_triggers=True anyway). skip_triggers=False mimics
  the real simulator parking forever on the first wait_for_trigger: nothing
  from that point on is scheduled.
* Truncation mimics the real simulator: samples are cut at duration_ns;
  report entries that START at or after duration_ns are dropped, entries
  that straddle it are reported with their full length.

Run the tests / smoke from the workspace root:
    .venv/Scripts/python.exe -m pytest k-exp/tests/opx_sim_fixture.py -q
    .venv/Scripts/python.exe k-exp/tests/opx_sim_fixture.py
(The file is not named test_*.py, so a bare `pytest k-exp/tests` does not
collect it -- pass the path explicitly.)
"""

import os
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import pytest

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
except Exception:   # pragma: no cover -- e.g. exec'd without __file__
    pass

from kexp.control.opx.trace_log import (OpLog, PHASE_PROLOGUE,
                                        PHASE_HANDSHAKE, PHASE_BODY,
                                        PHASE_EPILOGUE)

CON = 'con1'
_PULSER = {'controllerName': CON, 'pulserIndex': 0}
_IQ_SINGLE = {'isPartOfIq': False, 'isI': False, 'isQ': False}


# ---------------------------------------------------------------------------
# config helpers
# ---------------------------------------------------------------------------

def fake_config(a_80=0.25, a_150=0.3, f_80=80.e6, f_150=150.e6,
                t_acquire=5.e-6):
    """The K-machine QUA config, built by the REAL
    kexp.control.opx.opx_config.build_opx_config from a stub experiment (the
    same stub shape test_opx uses), so the structure cannot drift from what
    the lab runs: raman_80/raman_150 sticky analog on ports 1/2,
    raman_switch/imaging_switch sticky digital on ports 1/2 (block/pass
    16 ns), artiq_handback on port 3 (200 ns trigger), apd on digital port 4
    + analog input 1 with time_of_flight 200 and a 5000 ns acquire pulse."""
    from kexp.control.opx.opx_config import build_opx_config
    # the raman IFs come out of the real RamanBeamPair split: with centers
    # f_150/f_80, the transition 2*(f_150 - f_80) is its zero-offset point,
    # so the IFs are exactly f_150 and f_80
    ex = fake_raman_expt(f_80=f_80, f_150=f_150, a_80=a_80, a_150=a_150,
                         frequency_raman_transition=2. * (f_150 - f_80))
    p = ex.params
    p.t_imaging_pulse_apd_abs = t_acquire
    p.t_opx_integration_start = 0.
    p.t_opx_integration_len = t_acquire
    # the handshake params (read by kexp_channel_map, not by the config);
    # the two-sided split of ExptParams, 2026-09-24
    p.t_opx_handoff_artiq_side = 350.e-9
    p.t_opx_handoff_opx_side = 1.e-6
    p.t_opx_handback_artiq_trigger_receive_latency = 1.e-6
    p.t_opx_handback_artiq_rtio_delay = 2.e-6
    p.t_opx_handback_switch_fall_delay = 2.e-6
    return build_opx_config(ex)


def config_pulse(config, element, op):
    """The pulse dict an element's operation plays (pulse names follow the
    <element>.<op>.pulse rule; look them up through the element, never by
    literal name)."""
    return config['pulses'][config['elements'][element]['operations'][op]]


def fake_dds(frequency, amplitude, aom_order=1):
    """A dds channel stub with what RamanBeamPair reads on the host."""
    dev = SimpleNamespace(sysclk_per_mu=1,
                          frequency_to_ftw=lambda f: 0,
                          turns_to_pow=lambda t: 0,
                          amplitude_to_asf=lambda a: 0)
    return SimpleNamespace(frequency=frequency, amplitude=amplitude,
                           aom_order=aom_order, dds_device=dev)


def fake_raman_expt(f_80=80.e6, f_150=150.e6, a_80=0.337, a_150=0.324,
                    frequency_raman_transition=119.4639e6):
    """Stub experiment carrying dds.raman_80_plus / raman_150_plus and a
    REAL waxx RamanBeamPair wired like kexp/base/devices.py (dds0 = 150,
    dds1 = 80), so the OPX config runs the same split as the kernel."""
    from waxx.control.raman_beams import RamanBeamPair
    dds = SimpleNamespace(raman_80_plus=fake_dds(f_80, a_80),
                          raman_150_plus=fake_dds(f_150, a_150))
    params = SimpleNamespace(
        frequency_raman_transition=frequency_raman_transition)
    raman = RamanBeamPair(dds0=dds.raman_150_plus, dds1=dds.raman_80_plus,
                          dds_sw=SimpleNamespace(), params=params)
    return SimpleNamespace(params=params, p=params, dds=dds, raman=raman)


def _port_num(p):
    """(con, port) tuple / int / '1' -> int port."""
    if isinstance(p, (tuple, list)):
        p = p[-1]
    return int(p)


def _digital_ports(el_cfg):
    return [_port_num(v['port']) for v in el_cfg.get('digitalInputs', {}).values()]


def _analog_port(el_cfg):
    si = el_cfg.get('singleInput')
    return None if si is None else _port_num(si['port'])


def _marker_levels(config, marker_name, length):
    """Digital marker samples [(level, ns), ...] (ns = 0: rest of the pulse)
    -> uint8 level array of `length` ns."""
    samples = config['digital_waveforms'][marker_name]['samples']
    out = np.zeros(int(length), dtype=np.uint8)
    t = 0
    for level, ns in samples:
        if t >= length:
            break
        end = length if int(ns) == 0 else min(length, t + int(ns))
        out[t:end] = 1 if level else 0
        t = end
    return out


def _const_sample(config, wf_name):
    wf = config['waveforms'][wf_name]
    if wf.get('type') != 'constant':
        raise NotImplementedError(
            f"offline sim supports constant waveforms only ({wf_name!r} is "
            f"{wf.get('type')!r})")
    return float(wf['sample'])


# ---------------------------------------------------------------------------
# execution stream
# ---------------------------------------------------------------------------

def _stream(log: OpLog, n_shots):
    """(record, shot) in execution order: prologue once, per-shot records
    (handshake + body) for each shot honoring the executes mask, epilogue
    once. 'if' records are no-ops and dropped here (other control-flow
    kinds -- 'for', 'assign', 'declare', 'save' -- are skipped by the
    scheduler)."""
    pre = [r for r in log.records if r.phase == PHASE_PROLOGUE]
    per = [r for r in log.records if r.phase in (PHASE_HANDSHAKE, PHASE_BODY)]
    post = [r for r in log.records if r.phase == PHASE_EPILOGUE]
    for r in pre:
        yield r, 0
    for shot in range(n_shots):
        for r in per:
            if r.kind == 'if' or not r.executes_on(shot):
                continue
            yield r, shot
    for r in post:
        yield r, max(n_shots - 1, 0)


def _col_on(col, shot):
    c = np.atleast_1d(col)
    return c[int(shot)] if c.size > 1 else c[0]


@dataclass
class _Seg:
    """One stretch of synthesized analog tone on an element."""
    t0: int
    t1: 'int | None'          # None: open (sticky, until changed)
    amp: float
    freq: float
    phase: float              # rad
    origin: int               # ns, phase origin (reset_if_phase)
    ramp: bool = False        # linear ramp amp -> 0 over [t0, t1)


@dataclass
class _AnalogState:
    freq: float
    phase: float = 0.
    origin: int = 0
    amp: float = 0.
    sticky: bool = False
    ramp_ns: int = 0
    open_seg: 'int | None' = None     # index into segs of the held tone
    segs: list = field(default_factory=list)

    def close(self, t):
        if self.open_seg is not None:
            self.segs[self.open_seg].t1 = int(t)
            self.open_seg = None

    def reopen(self, t):
        """Held tone changes parameters at t (frequency/phase/frame)."""
        if self.open_seg is None:
            return
        self.close(t)
        self.segs.append(_Seg(int(t), None, self.amp, self.freq, self.phase,
                              self.origin))
        self.open_seg = len(self.segs) - 1


# ---------------------------------------------------------------------------
# the simulator
# ---------------------------------------------------------------------------

def simulate_offline(log, config, n_shots, duration_ns, skip_triggers=True,
                     _provenance=None, _end=None):
    """Replay `log` against `config` for `n_shots` loop iterations over a
    `duration_ns` window. Returns (SimulatorSamples, WaveformReport) built
    from the real qm classes. See the module docstring for the semantics.

    _provenance: optional list, filled with (report_entry, record_index,
    shot) for every reported entry. _end: optional dict, filled with
    {'t_end_ns': latest element clock, 'parked': bool}.
    """
    from qm.waveform_report import (PlayedAnalogWaveform,
                                    PlayedDigitalWaveform, AdcAcquisition,
                                    Event, WaveformReport)
    from qm.simulate import SimulatorSamples, SimulatorControllerSamples

    n_shots = int(n_shots)
    N = int(duration_ns)
    if n_shots > log.n_shots:
        raise ValueError(f"n_shots={n_shots} > the {log.n_shots} shots the "
                         f"log was traced for (per-shot tables would run out)")

    els = config['elements']
    clk = {e: 0 for e in els}
    analog = {}
    for e, ec in els.items():
        if 'singleInput' in ec:
            st = ec.get('sticky', {}) or {}
            analog[e] = _AnalogState(
                freq=float(ec.get('intermediate_frequency', 0.)),
                sticky=bool(st.get('analog', False)),
                ramp_ns=int(st.get('duration', 0)))
    digital_plays = {e: [] for e in els}     # (t0, length, marker)

    a_wfs, d_wfs, adcs, events = [], [], [], []
    prov = []
    parked = False

    def report_digital(e, pulse_name, marker, t0, length, rec, shot):
        if t0 >= N:
            return
        wf = PlayedDigitalWaveform(
            waveform_name=marker, pulse_name='OriginPulseName=' + pulse_name,
            length=int(length), timestamp=int(t0), iq_info=dict(_IQ_SINGLE),
            element=e, output_ports=_digital_ports(els[e]), controller=CON,
            pulser=dict(_PULSER), fem=1)
        d_wfs.append(wf)
        prov.append((wf, rec.index, shot))

    for rec, shot in _stream(log, n_shots):
        k, e = rec.kind, rec.element

        if k == 'wait_for_trigger':
            if skip_triggers:
                continue
            parked = True          # the real simulator parks here forever
            break

        if k == 'align':
            t = max(clk.values()) if clk else 0
            for x in clk:
                clk[x] = t
            continue

        if k == 'wait':
            names = rec.extra.get('elements') or ([e] if e else [])
            d = rec.duration_on(shot) or 0
            for x in names:
                clk[x] += 4 * int(d)
            continue

        if k in ('save', 'if', 'for', 'assign', 'declare'):
            # no timeline effect: QUA control flow / variable bookkeeping
            # (ctx.for_range, ctx.save, ctx.assign) is replayed by the
            # OpLog's executes mask, not scheduled
            continue

        ec = els[e]

        if k == 'play':
            pulse_name = ec['operations'][rec.op]
            pc = config['pulses'][pulse_name]
            d = rec.duration_on(shot)
            length = 4 * int(d) if d is not None else int(pc['length'])
            t0 = clk[e]
            clk[e] = t0 + length
            marker = pc.get('digital_marker')
            if marker is not None and 'digitalInputs' in ec:
                digital_plays[e].append((t0, length, marker))
                report_digital(e, pulse_name, marker, t0, length, rec, shot)
            wfs = pc.get('waveforms')
            if wfs:
                port = _analog_port(ec)
                wf_name = wfs.get('single')
                # the builder's latch carries its amp() factor in the log
                amp = (_const_sample(config, wf_name)
                       * float(rec.extra.get('amp_scale', 1.)))
                st = analog[e]
                st.close(t0)
                st.amp = amp
                st.segs.append(_Seg(t0, None if st.sticky else t0 + length,
                                    amp, st.freq, st.phase, st.origin))
                if st.sticky:
                    st.open_seg = len(st.segs) - 1
                if t0 < N:
                    wf = PlayedAnalogWaveform(
                        waveform_name=wf_name,
                        pulse_name='OriginPulseName=' + pulse_name,
                        length=int(length), timestamp=int(t0),
                        iq_info=dict(_IQ_SINGLE), element=e,
                        output_ports=[port], controller=CON,
                        pulser=dict(_PULSER), fem=1,
                        current_amp_elements=[amp],
                        current_dc_offset_by_port={str(port): 0.0},
                        current_intermediate_frequency=float(st.freq),
                        current_frame=[0.0],
                        current_correction_elements=[1.0],
                        chirp_info=None, current_phase=0)
                    a_wfs.append(wf)
                    prov.append((wf, rec.index, shot))
            continue

        if k == 'measure':
            pulse_name = ec['operations'][rec.op]
            pc = config['pulses'][pulse_name]
            length = int(pc['length'])
            t0 = clk[e]
            clk[e] = t0 + length
            marker = pc.get('digital_marker')
            if marker is not None and 'digitalInputs' in ec:
                digital_plays[e].append((t0, length, marker))
                report_digital(e, pulse_name, marker, t0, length, rec, shot)
            start = t0 + int(ec.get('time_of_flight', 0))
            if start < N:
                adc = AdcAcquisition(
                    start_time=int(start), end_time=int(start + length),
                    process='integration', pulser=dict(_PULSER),
                    quantum_element=e,
                    adc_ports=[_port_num(p) for p in ec.get('outputs', {}).values()],
                    controller=CON, fem=1, element=e)
                adcs.append(adc)
                prov.append((adc, rec.index, shot))
            continue

        if k == 'reset_if_phase':
            t = clk[e]
            if e in analog:
                st = analog[e]
                st.origin = int(t)
                st.reopen(t)
            if t < N:
                ev = Event(name='phase_reset', timestamp=int(t), controller=CON,
                           fem=1, element=e, is_i=False, is_q=False)
                events.append(ev)
                prov.append((ev, rec.index, shot))
            continue

        if k == 'update_frequency':
            if e in analog and 'frequency_hz' in rec.extra:
                st = analog[e]
                st.freq = float(_col_on(rec.extra['frequency_hz'], shot))
                st.reopen(clk[e])
            continue

        if k == 'frame_rotation_2pi':
            if e in analog and 'turns' in rec.extra:
                st = analog[e]
                st.phase += 2 * np.pi * float(_col_on(rec.extra['turns'], shot))
                st.reopen(clk[e])
            continue

        if k == 'reset_frame':
            if e in analog:
                st = analog[e]
                st.phase = 0.
                st.reopen(clk[e])
            continue

        if k == 'ramp_to_zero':
            if e in analog and analog[e].sticky:
                st = analog[e]
                t0 = clk[e]
                if st.open_seg is not None:
                    st.close(t0)
                    st.segs.append(_Seg(t0, t0 + st.ramp_ns, st.amp, st.freq,
                                        st.phase, st.origin, ramp=True))
                st.amp = 0.
                clk[e] = t0 + st.ramp_ns
            continue

        raise ValueError(f"offline sim: unhandled op kind {k!r}")

    # ---------------- samples ----------------
    ctrl = config['controllers'][CON]
    a_ports = {int(p): np.zeros(N, dtype=np.float64)
               for p in ctrl.get('analog_outputs', {})}
    d_ports = {int(p): np.zeros(N, dtype=bool)
               for p in ctrl.get('digital_outputs', {})}

    for e, st in analog.items():
        port = _analog_port(els[e])
        arr = a_ports.setdefault(port, np.zeros(N, dtype=np.float64))
        for s in st.segs:
            a = max(s.t0, 0)
            b = min(N if s.t1 is None else s.t1, N)
            if b <= a:
                continue
            t = np.arange(a, b, dtype=np.float64)
            v = s.amp * np.sin(2 * np.pi * s.freq * (t - s.origin) * 1e-9
                               + s.phase)
            if s.ramp and s.t1 > s.t0:
                v *= 1. - (t - s.t0) / (s.t1 - s.t0)
            arr[a:b] += v

    for e, plays in digital_plays.items():
        if not plays:
            continue
        ec = els[e]
        sticky = bool((ec.get('sticky', {}) or {}).get('digital', False))
        line = np.zeros(N, dtype=np.uint8)
        for t0, length, marker in plays:        # time-ordered per element
            if t0 >= N:
                break
            lv = _marker_levels(config, marker, length)
            b = min(t0 + length, N)
            line[t0:b] = lv[:b - t0]
            if sticky and b < N:
                line[b:] = lv[-1] if length else 0
        for port in _digital_ports(ec):
            d_ports.setdefault(port, np.zeros(N, dtype=bool))
            d_ports[port] |= line.astype(bool)

    samples = SimulatorSamples({CON: SimulatorControllerSamples(
        analog={str(p): v.astype(np.float32) for p, v in sorted(a_ports.items())},
        digital={str(p): v for p, v in sorted(d_ports.items())})})

    report = WaveformReport(
        job_id='offline',
        analog_waveforms=sorted(a_wfs, key=lambda w: w.timestamp),
        digital_waveforms=sorted(d_wfs, key=lambda w: w.timestamp),
        adc_acquisitions=sorted(adcs, key=lambda a: a.start_time),
        events=sorted(events, key=lambda ev: ev.timestamp))

    if _provenance is not None:
        _provenance.extend(prov)
    if _end is not None:
        _end['t_end_ns'] = int(max(clk.values()) if clk else 0)
        _end['parked'] = parked
    return samples, report


class OfflineJob:
    """Duck-types qm's SimulatedJob for a consumer that only reads the
    simulation results. Also carries the inputs (log, config, program) and
    `provenance`: [(report_entry, OpRecord.index, shot)] -- fixture-only
    ground truth, the real simulator has no such thing."""

    def __init__(self, samples, report, log=None, config=None, program=None,
                 ctx=None, provenance=None, t_end_ns=None, parked=False,
                 n_shots=None, duration_ns=None):
        self._samples = samples
        self._report = report
        self.log = log
        self.config = config
        self.program = program
        self.ctx = ctx
        self.provenance = provenance if provenance is not None else []
        self.t_end_ns = t_end_ns
        self.parked = parked
        self.n_shots = n_shots
        self.duration_ns = duration_ns
        self.id = 'offline'

    def get_simulated_samples(self):
        return self._samples

    def get_simulated_waveform_report(self):
        return self._report

    # qm's job API also exposes these names in some versions
    simulated_analog_waveforms = None
    simulated_digital_waveforms = None


def simulate_job(log, config, n_shots, duration_ns, skip_triggers=True,
                 program=None, ctx=None) -> OfflineJob:
    """simulate_offline wrapped in an OfflineJob (with provenance)."""
    prov, end = [], {}
    samples, report = simulate_offline(log, config, n_shots, duration_ns,
                                       skip_triggers=skip_triggers,
                                       _provenance=prov, _end=end)
    return OfflineJob(samples, report, log=log, config=config,
                      program=program, ctx=ctx, provenance=prov,
                      t_end_ns=end['t_end_ns'], parked=end['parked'],
                      n_shots=int(n_shots), duration_ns=int(duration_ns))


def trace_and_simulate(sequence, xvars, duration_ns, n_shots=None,
                       skip_triggers=True, config=None) -> OfflineJob:
    """Trace `sequence` over test_opx.FakeExpt(xvars) with test_opx.make_map()
    and simulate it offline. xvars: [(key, values), ...] (unshuffled, last
    innermost). config defaults to fake_config()."""
    from test_opx import FakeExpt, make_map
    from kexp.control.opx.params_bridge import build_shot_tables
    from kexp.control.opx.builder import OPXProgramBuilder

    ex = FakeExpt(list(xvars))
    tables = build_shot_tables(ex)
    builder = OPXProgramBuilder(sequence, make_map(), tables, tables.n_shots)
    prog, ctx = builder.trace(skip_triggers=skip_triggers)
    cfg = config if config is not None else fake_config()
    n = tables.n_shots if n_shots is None else int(n_shots)
    return simulate_job(builder.log, cfg, n, duration_ns,
                        skip_triggers=skip_triggers, program=prog, ctx=ctx)


def predicted_digital_plays(log, config, n_shots, port):
    """Timing-free prediction: how many digital waveforms the log puts on
    digital `port` over n_shots (plays + measures on elements wired to that
    port whose pulse has a digital marker). Independent of the scheduler --
    only valid when the window holds the whole run."""
    els = config['elements']
    n = 0
    for rec, _shot in _stream(log, n_shots):
        if rec.kind not in ('play', 'measure') or rec.element is None:
            continue
        ec = els[rec.element]
        if port not in _digital_ports(ec):
            continue
        pc = config['pulses'][ec['operations'][rec.op]]
        if pc.get('digital_marker') is not None:
            n += 1
    return n


# ---------------------------------------------------------------------------
# smoke
# ---------------------------------------------------------------------------

def _smoke():
    from collections import Counter
    from kexp.experiments.opx_sequences.rabi import rabi_raman_apd

    xv = [('t_raman_pulse', [0., 4.e-6, 8.e-6])]
    job = trace_and_simulate(rabi_raman_apd, xv, duration_ns=600_000,
                             n_shots=3)
    rep = job.get_simulated_waveform_report()
    kinds = Counter()
    kinds['analog'] = len(rep.analog_waveforms)
    kinds['digital'] = len(rep.digital_waveforms)
    kinds['adc'] = len(rep.adc_acquisitions)
    kinds['event'] = len(rep.events)
    print(f"[smoke] 600 us window, run ends at {job.t_end_ns} ns; "
          f"report counts: {dict(kinds)}")
    print("[smoke] ops by kind in the log:",
          dict(Counter(r.kind for r in job.log.records)))
    entries = sorted(
        [(w.timestamp, 'A', w.element, w.pulse_name, w.length) for w in rep.analog_waveforms]
        + [(w.timestamp, 'D', w.element, w.pulse_name, w.length) for w in rep.digital_waveforms]
        + [(a.start_time, 'ADC', a.element, a.process, a.end_time - a.start_time) for a in rep.adc_acquisitions]
        + [(ev.timestamp, 'EV', ev.element, ev.name, 0) for ev in rep.events])
    for ent in entries[:10]:
        print("   ", ent)

    port1 = lambda r: sum(1 for w in r.digital_waveforms if 1 in w.output_ports)
    pred = predicted_digital_plays(job.log, job.config, 3, port=1)
    got_600 = port1(rep)
    print(f"[smoke] port-1 digital waveforms: 600 us window {got_600}, "
          f"log predicts {pred} for the whole run")
    assert got_600 <= pred
    # the whole run needs ~810 us; the equality check needs a window that
    # holds it all
    full = trace_and_simulate(rabi_raman_apd, xv,
                              duration_ns=job.t_end_ns + 1000, n_shots=3)
    got_full = port1(full.get_simulated_waveform_report())
    print(f"[smoke] full window ({full.duration_ns} ns): port-1 digital "
          f"waveforms {got_full} == predicted {pred}")
    assert got_full == pred, (got_full, pred)
    print("[smoke] OK")


if __name__ == '__main__':
    _smoke()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def _seq(func, name, claims=('raman',), measurements=None):
    from kexp.control.opx.sequence import OPXSequence
    return OPXSequence(func, name=name, claims=claims,
                       measurements=measurements)


def _rabi_only(ctx):
    ctx.raman_pulse(ctx.p.t_raman_pulse)


def _triggers(rep):
    return [w for w in rep.digital_waveforms if w.element == 'artiq_handback']


def _exposures(rep, element='raman_switch'):
    """'pass' plays longer than one 16 ns edge: body exposures (the
    hand-back release is a 16 ns pass)."""
    return [w for w in rep.digital_waveforms
            if w.element == element and w.pulse_name.endswith('.pass.pulse')
            and w.length > 16]


def _per_shot(entries, triggers):
    """Split entries at the hand-back trigger timestamps."""
    edges = [t.timestamp for t in triggers]
    out = [[] for _ in edges]
    for w in entries:
        for i, te in enumerate(edges):
            if w.timestamp < te:
                out[i].append(w)
                break
    return out


def test_zero_length_pulse_plays_nothing():
    seq = _seq(_rabi_only, '_sim_rabi0')
    job = trace_and_simulate(seq, [('t_raman_pulse', [0., 4.e-6, 8.e-6])],
                             duration_ns=200_000)
    rep = job.get_simulated_waveform_report()
    trig = _triggers(rep)
    assert len(trig) == 3
    shots = _per_shot(_exposures(rep), trig)
    assert [len(s) for s in shots] == [0, 1, 1]
    # and no 'pass' at all on raman_switch before shot 0's hand-back
    assert not [w for w in rep.digital_waveforms
                if w.element == 'raman_switch' and 'pass' in w.pulse_name
                and w.timestamp < trig[0].timestamp]


def test_exposure_durations_equal_xvar():
    xv = [1.e-6, 2.5e-6, 4.e-6]
    seq = _seq(_rabi_only, '_sim_rabi_dur')
    job = trace_and_simulate(seq, [('t_raman_pulse', xv)],
                             duration_ns=200_000)
    rep = job.get_simulated_waveform_report()
    shots = _per_shot(_exposures(rep), _triggers(rep))
    assert [[w.length for w in s] for s in shots] == [
        [int(round(x * 1e9))] for x in xv]
    # the digital samples agree with the report
    d1 = job.get_simulated_samples().con1.digital['1']
    for s in shots:
        w = s[0]
        assert not d1[w.timestamp:w.timestamp + w.length].any()   # low = pass
        assert d1[w.timestamp + w.length + 1]                     # re-blocked


def test_adc_window_is_time_of_flight_after_marker():
    from kexp.experiments.opx_sequences.rabi import rabi_raman_apd
    job = trace_and_simulate(rabi_raman_apd,
                             [('t_raman_pulse', [0., 4.e-6, 8.e-6])],
                             duration_ns=1_000_000)
    rep = job.get_simulated_waveform_report()
    tof = job.config['elements']['apd']['time_of_flight']
    acq_len = config_pulse(job.config, 'apd', 'acquire')['length']
    markers = [w for w in rep.digital_waveforms if w.element == 'apd']
    adcs = rep.adc_acquisitions
    assert len(markers) == len(adcs) == 4 * 3
    for m, a in zip(markers, adcs):
        assert a.start_time == m.timestamp + tof
        assert a.end_time - a.start_time == acq_len == m.length
        assert m.output_ports == [4] and a.adc_ports == [1]


def test_truncation_drops_later_pulses_and_keeps_straddlers():
    from kexp.experiments.opx_sequences.rabi import rabi_raman_apd
    xv = [('t_raman_pulse', [0., 4.e-6, 8.e-6])]
    full = trace_and_simulate(rabi_raman_apd, xv, duration_ns=1_000_000)
    all_wfs = full.get_simulated_waveform_report().digital_waveforms
    # cut in the middle of some pulse longer than 1 us
    target = next(w for w in all_wfs if w.length > 1000
                  and w.timestamp > 300_000)
    cut = target.timestamp + target.length // 2
    part = trace_and_simulate(rabi_raman_apd, xv, duration_ns=cut)
    rep = part.get_simulated_waveform_report()
    assert all(w.timestamp < cut for w in rep.digital_waveforms)
    assert all(a.start_time < cut for a in rep.adc_acquisitions)
    assert len(rep.digital_waveforms) == sum(1 for w in all_wfs
                                             if w.timestamp < cut)
    assert len(rep.digital_waveforms) < len(all_wfs)
    straddler = [w for w in rep.digital_waveforms
                 if w.element == target.element
                 and w.timestamp == target.timestamp]
    assert straddler and straddler[0].length == target.length
    s = part.get_simulated_samples().con1
    assert all(len(v) == cut for v in s.analog.values())
    assert all(len(v) == cut for v in s.digital.values())


def test_sticky_digital_level_holds_between_plays():
    seq = _seq(_rabi_only, '_sim_rabi_hold')
    job = trace_and_simulate(seq, [('t_raman_pulse', [2.e-6, 3.e-6])],
                             duration_ns=100_000)
    rep = job.get_simulated_waveform_report()
    d1 = job.get_simulated_samples().con1.digital['1']
    sw = [w for w in rep.digital_waveforms if w.element == 'raman_switch']
    for a, b in zip(sw, sw[1:]):
        level = a.pulse_name.endswith('.block.pulse')
        seg = d1[a.timestamp:b.timestamp]
        assert seg.size > 0 and (seg.all() if level else not seg.any()), \
            (a.pulse_name, a.timestamp, b.timestamp)
    # after the last release the line stays low (pass) to the end
    assert not d1[sw[-1].timestamp:].any()
    # non-sticky hand-back trigger: high for exactly its 200 ns
    d3 = job.get_simulated_samples().con1.digital['3']
    t = _triggers(rep)[0]
    assert d3[t.timestamp:t.timestamp + t.length].all()
    assert not d3[t.timestamp + t.length:t.timestamp + t.length + 500].any()
    assert int(d3.sum()) == sum(w.length for w in _triggers(rep))


def test_analog_port_carries_latched_sine():
    seq = _seq(_rabi_only, '_sim_rabi_sine')
    job = trace_and_simulate(seq, [('t_raman_pulse', [2.e-6, 3.e-6])],
                             duration_ns=200_000)
    s = job.get_simulated_samples().con1
    rep = job.get_simulated_waveform_report()
    a1 = np.asarray(s.analog['1'], dtype=float)
    a2 = np.asarray(s.analog['2'], dtype=float)
    latch = [w for w in rep.analog_waveforms if w.element == 'raman_80']
    assert len(latch) == 1 and latch[0].timestamp == 0
    assert latch[0].current_intermediate_frequency == 80_000_000
    win = a1[5_000:25_000]            # long after the 1 us latch: held
    # amplitude from the RMS over an integer number of periods (20 us =
    # 1600 periods at 80 MHz; 3000 at 150 MHz): the 1 GS/s grid only hits
    # the crest to within cos(2 pi * 0.02) at 80 MHz, so max() reads ~0.2%
    # low -- a sampling fact, bounded separately
    rms = lambda x: float(np.sqrt(np.mean(np.square(x))))
    assert np.sqrt(2) * rms(win) == pytest.approx(0.25, rel=1e-3)
    assert np.sqrt(2) * rms(a2[5_000:25_000]) == pytest.approx(0.3, rel=1e-3)
    assert 0.249 < np.max(win) <= 0.25 and -0.25 <= np.min(win) < -0.249
    spec = np.abs(np.fft.rfft(win))
    f = np.fft.rfftfreq(win.size, d=1e-9)
    assert f[np.argmax(spec)] == pytest.approx(80.e6, rel=1e-3)
    # ramp_to_zero at the end of the run, then silence
    t_end = job.t_end_ns
    assert np.all(a1[t_end:] == 0.)
    assert np.max(np.abs(a1[t_end - 100:t_end])) < 0.25


def test_handback_hold_counts_from_the_trigger_edge():
    # the blocks fall exactly t_handback_hold_s after each hand-back
    # trigger's rising edge, and the analog drives are left alone for the
    # same hold: the last shot's ramp_to_zero starts then, not at the
    # trigger (ARTIQ still routes the AOs to the OPX until its take-back)
    from test_opx import make_map
    seq = _seq(_rabi_only, '_sim_hold')
    job = trace_and_simulate(seq, [('t_raman_pulse', [2.e-6, 3.e-6])],
                             duration_ns=200_000)
    rep = job.get_simulated_waveform_report()
    hold_ns = int(round(make_map().t_handback_hold_s * 1e9))
    trig = _triggers(rep)
    assert len(trig) == 2
    for sw in ('raman_switch', 'imaging_switch'):
        releases = [w.timestamp for w in rep.digital_waveforms
                    if w.element == sw and w.pulse_name.endswith('.pass.pulse')
                    and w.length == 16]
        assert releases == [t.timestamp + hold_ns for t in trig], sw
    t_e = trig[-1].timestamp
    ramp_ns = job.config['elements']['raman_80']['sticky']['duration']
    assert job.t_end_ns == t_e + hold_ns + ramp_ns
    s = job.get_simulated_samples().con1
    rms = lambda x: float(np.sqrt(np.mean(np.square(x))))
    for port, amp in (('1', 0.25), ('2', 0.3)):
        a = np.asarray(s.analog[port], dtype=float)
        # full tone through the whole hold (10 us = integer periods at 80
        # and 150 MHz), silence after the ramp
        assert np.sqrt(2) * rms(a[t_e:t_e + hold_ns]) == \
            pytest.approx(amp, rel=1e-3), port
        assert np.all(a[t_e + hold_ns + ramp_ns:] == 0.), port


def test_phase_reset_events_and_job_ducktype():
    def body(ctx):
        ctx.raman_phase_reset()
        ctx.raman_pulse(ctx.p.t_raman_pulse)
    seq = _seq(body, '_sim_phase')
    job = trace_and_simulate(seq, [('t_raman_pulse', [1.e-6, 2.e-6])],
                             duration_ns=100_000)
    from qm.waveform_report import WaveformReport, Event
    from qm.simulate import SimulatorSamples
    rep = job.get_simulated_waveform_report()
    assert isinstance(rep, WaveformReport)
    assert isinstance(job.get_simulated_samples(), SimulatorSamples)
    evs = rep.events
    assert len(evs) == 4 and all(isinstance(e, Event) for e in evs)
    assert {e.element for e in evs} == {'raman_80', 'raman_150'}
    assert all(e.name == 'phase_reset' for e in evs)
    assert set(rep.elements_in_report) >= {'raman_80', 'raman_switch',
                                           'artiq_handback'}


def test_wait_for_trigger_parks_without_skip():
    seq = _seq(_rabi_only, '_sim_park')
    job = trace_and_simulate(seq, [('t_raman_pulse', [1.e-6, 2.e-6])],
                             duration_ns=50_000, skip_triggers=False)
    rep = job.get_simulated_waveform_report()
    assert job.parked
    # only the prologue latch ran; the loop parked on its first trigger
    assert {w.element for w in rep.analog_waveforms} == {'raman_80',
                                                         'raman_150'}
    assert rep.digital_waveforms == []

