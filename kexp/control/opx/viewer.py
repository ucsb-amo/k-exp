"""OPX simulation -> seqview bundle: every simulated pulse tied to the line
of sequence code (and of generated QUA) that made it.

The QOP simulator returns per-port samples and a waveform report (every
played pulse with element, pulse name, timestamp, length; ADC windows;
phase-reset events). The builder's trace-time op log (trace_log.py) is the
same program in emission order with provenance. This module walks the two
side by side -- per element, in order, checking pulse names -- and produces
a machine-agnostic bundle (waxx.util.seqview.bundle) that the viewer window
draws:

* semantic lanes: sequence steps (one bar per macro call), light-ON
  exposures per beam role, ADC acquire windows, hand-back trigger;
* physical lanes: every digital output as an edge list from the samples,
  every analog output as samples with its event markers (phase resets,
  frequency / frame changes);
* shots and handshake framing bands, the per-shot parameter table, source
  texts (sequence, simulated QUA, real QUA, config), warnings.

What the simulator reported is the truth drawn on screen. The op log only
annotates it, and every disagreement (a pulse the samples do not show, a
pulse the program expected but the window cut off, a length that was
rounded to the 4 ns grid) is a warning, never silently reconciled.

kexp-specific only in what it imports from the opx package; the lane
vocabulary (roles, switches, ADC) comes from the channel map, not from
hard-coded element names.
"""

import os
import pprint
import re
import sys
import time
from collections import defaultdict

import numpy as np

from kexp.control.opx.trace_log import (PHASE_PROLOGUE, PHASE_HANDSHAKE,
                                        PHASE_BODY, PHASE_EPILOGUE,
                                        EVENT_KINDS)
from kexp.control.opx.units import CLOCK_NS

# Okabe-Ito, one hue per function (see the design notes in seqview/README)
COLORS = {
    'steps': '#d9d9d9',
    'raman': '#e69f00',
    'imaging': '#56b4e9',
    'adc': '#009e73',
    'handback': '#cc79a7',
    'analog': '#f0e442',
    'framing': '#8a8a8a',
    'wait': '#6f7a86',
}
_ROLE_COLORS = ['#e69f00', '#56b4e9', '#d55e00', '#0072b2', '#f0e442']

_ORIGIN_PREFIX = 'OriginPulseName='


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------

def fmt_ns(ns):
    """A duration/time in ns as a compact SI string."""
    ns = float(ns)
    a = abs(ns)
    if a >= 1e6:
        return f"{ns / 1e6:.6g} ms"
    if a >= 1e3:
        return f"{ns / 1e3:.6g} µs"
    return f"{ns:.6g} ns"


def fmt_param(name, value):
    """A parameter value with the unit its name implies (waxa.units)."""
    try:
        from waxa.units import unit_for_param, mult_for
        unit = unit_for_param(name, [value])
        if unit:
            return f"{float(value) * mult_for(unit):.6g} {unit}"
    except Exception:
        pass
    return f"{float(value):.6g}"


def _strip_origin(name):
    return str(name).removeprefix(_ORIGIN_PREFIX)


# ---------------------------------------------------------------------------
# config lookups
# ---------------------------------------------------------------------------

class _Config:
    def __init__(self, config):
        self.c = config or {}
        self.elements = self.c.get('elements', {})
        self.pulses = self.c.get('pulses', {})

    def pulse_name(self, element, op):
        try:
            return self.elements[element]['operations'][op]
        except KeyError:
            return None

    def pulse_length(self, element, op):
        p = self.pulse_name(element, op)
        try:
            return int(self.pulses[p]['length'])
        except (KeyError, TypeError):
            return None

    def digital_port(self, element):
        e = self.elements.get(element, {})
        for v in e.get('digitalInputs', {}).values():
            port = v.get('port')
            if port:
                return str(port[1])
        return None

    def analog_port(self, element):
        e = self.elements.get(element, {})
        si = e.get('singleInput')
        if si and si.get('port'):
            return str(si['port'][1])
        return None

    def adc_port(self, element):
        e = self.elements.get(element, {})
        for v in e.get('outputs', {}).values():
            return str(v[1])
        return None

    def is_sticky_digital(self, element):
        return bool(self.elements.get(element, {}).get('sticky', {})
                    .get('digital', False))

    def time_of_flight(self, element):
        return int(self.elements.get(element, {}).get('time_of_flight', 0))

    def intermediate_frequency(self, element):
        return self.elements.get(element, {}).get('intermediate_frequency')

    def analog_amplitude(self, element, op='cw'):
        try:
            wf = self.pulses[self.pulse_name(element, op)]['waveforms']['single']
            return float(self.c['waveforms'][wf]['sample'])
        except (KeyError, TypeError):
            return None


# ---------------------------------------------------------------------------
# execution stream: the op log unrolled over the simulated shots
# ---------------------------------------------------------------------------

def expand_execution(log, n_shots):
    """[(record, shot)] in OPX execution order: prologue once, then the
    per-shot records for every shot (skipping the ones an if_ guard turns
    off on that shot), then the epilogue once. shot is None outside the
    loop."""
    recs = list(log.records)
    pro = [r for r in recs if r.phase == PHASE_PROLOGUE]
    per = [r for r in recs if r.phase in (PHASE_HANDSHAKE, PHASE_BODY)]
    epi = [r for r in recs if r.phase == PHASE_EPILOGUE]
    out = [(r, None) for r in pro]
    for s in range(int(n_shots)):
        for r in per:
            if r.kind == 'if':
                continue
            if r.executes_on(s):
                out.append((r, s))
    out += [(r, None) for r in epi]
    return out


# ---------------------------------------------------------------------------
# QUA text line mapping
# ---------------------------------------------------------------------------

_STMT = re.compile(
    r"^\s*(?:with\s+)?(play|wait|align|measure|save|wait_for_trigger"
    r"|ramp_to_zero|reset_if_phase|reset_frame|update_frequency"
    r"|frame_rotation_2pi|if_)\(")
_STOP = re.compile(r"^\s*(with\s+stream_processing\(|config\s*=)")


def qua_line_map(log, qua_text):
    """{record index: 1-based line in qua_text}. The serializer prints one
    statement per line in emission order, so the kind sequences must agree
    exactly; if they do not (a qm version that serializes differently) no
    mapping is returned and the caller warns."""
    if not qua_text:
        return {}, "no QUA text"
    stmts = []
    for i, line in enumerate(qua_text.splitlines(), start=1):
        if _STOP.match(line):
            break
        m = _STMT.match(line)
        if m:
            kind = m.group(1)
            stmts.append((i, 'if' if kind == 'if_' else kind))
    recs = [r for r in log.records if r.kind in dict.fromkeys(
        ('play', 'wait', 'align', 'measure', 'save', 'wait_for_trigger',
         'ramp_to_zero', 'reset_if_phase', 'reset_frame', 'update_frequency',
         'frame_rotation_2pi', 'if'))]
    if len(stmts) != len(recs):
        return {}, (f"QUA text has {len(stmts)} statements, the op log "
                    f"{len(recs)} -- line mapping disabled")
    out = {}
    for (line, kind), r in zip(stmts, recs):
        if kind != r.kind:
            return {}, (f"QUA statement kind {kind!r} at line {line} does "
                        f"not match op log kind {r.kind!r} -- line mapping "
                        f"disabled")
        out[r.index] = line
    return out, ''


# ---------------------------------------------------------------------------
# the bundle builder
# ---------------------------------------------------------------------------

class BundleBuilder:
    """Assemble one seqview bundle from a simulation.

    job:       qm SimulatedJob (or anything with get_simulated_samples /
               get_simulated_waveform_report)
    builder:   the OPXProgramBuilder that traced the *simulated* program
               (its .log, .tables, .n_shots)
    cmap:      ChannelMap; config: the QUA config dict
    """

    def __init__(self, job, builder, cmap, config, duration_ns,
                 qua_sim='', qua_real='', info=None, sequence=None):
        self.job = job
        self.builder = builder
        self.log = builder.log
        self.tables = builder.tables
        self.n_shots = int(builder.n_shots)
        self.cmap = cmap
        self.cfg = _Config(config)
        self.config = config
        self.duration_ns = float(duration_ns)
        self.qua_sim = qua_sim or ''
        self.qua_real = qua_real or ''
        self.info = dict(info or {})
        self.sequence = sequence if sequence is not None else builder.sequence

        self.warnings = []
        self.pulses = []
        self.events = []
        self.lanes = []
        self.arrays = {}
        self._lane_ids = {}
        self._adc_spans = {}      # (shot, call) -> [(t0, t1)] of ADC windows

    # ---- warnings --------------------------------------------------------
    def warn(self, text, level='warning'):
        self.warnings.append({'level': level, 'text': str(text)})

    # ---- roles / lanes ---------------------------------------------------
    def _role_of_element(self, element):
        for role, spec in self.cmap.channels.items():
            if element == spec.switch_element:
                return role, 'switch'
            if element in spec.analog_elements:
                return role, 'analog'
            if element == spec.measure_element:
                return role, 'measure'
        if element == self.cmap.handback_element:
            return 'handback', 'handback'
        return None, None

    def _role_color(self, role):
        if role in COLORS:
            return COLORS[role]
        roles = list(self.cmap.channels)
        try:
            return _ROLE_COLORS[roles.index(role) % len(_ROLE_COLORS)]
        except ValueError:
            return '#bbbbbb'

    def _add_lane(self, lane_id, label, kind, group, color, **kw):
        lane = {'id': lane_id, 'label': label, 'kind': kind, 'group': group,
                'color': color, 'element': None, 'port': None, 'role': None,
                'note': '', 'high_label': '', 'low_label': '',
                'samples': None, 'edges': None, 'level0': 0,
                'pulses': [], 'events': [], 'visible': True, 'height': 1.0}
        lane.update(kw)
        self.lanes.append(lane)
        self._lane_ids[lane_id] = lane
        return lane

    def _add_pulse(self, lane_id, **kw):
        p = {'id': len(self.pulses), 'lane': lane_id, 'element': None,
             'op': None, 'pulse_name': None, 't0': 0., 't1': 0.,
             'shot': None, 'phase': PHASE_BODY, 'macro': '', 'label': '',
             'value': None, 'value_str': '', 'requested_ns': None,
             'actual_ns': None, 'rounded': False, 'src_line': None,
             'src_lines': [], 'qua_line': None, 'note': '', 'data_key': '',
             'kind': 'play', 'color': self._lane_ids[lane_id]['color'],
             'text': '', 'truncated': False}
        p.update(kw)
        if p['t1'] < p['t0']:
            p['t1'] = p['t0']
        if p['t1'] > self.duration_ns:
            p['truncated'] = True
        self.pulses.append(p)
        self._lane_ids[lane_id]['pulses'].append(p['id'])
        return p

    def _add_event(self, lane_id, t, kind, label, detail='', src_line=None,
                   src_lines=None, qua_line=None, approx=False, shot=None):
        ev = {'id': len(self.events), 'lane': lane_id, 't': float(t),
              'kind': kind, 'label': label, 'detail': detail,
              'src_line': src_line, 'src_lines': list(src_lines or []),
              'qua_line': qua_line, 'approx': bool(approx), 'shot': shot}
        self.events.append(ev)
        self._lane_ids[lane_id]['events'].append(ev['id'])
        return ev

    # ---- provenance fields shared by pulses and events ------------------
    def _prov(self, rec, shot, qmap):
        src = rec.source
        value = rec.value_on(shot) if (rec.values is not None
                                       and shot is not None) else (
            rec.value_on(0) if rec.values is not None else None)
        vstr = ''
        if value is not None:
            vstr = (f"{rec.label} = {fmt_param(rec.label, value)}"
                    if rec.label and not rec.label.startswith('(')
                    else (f"{rec.label} = {fmt_ns(value * 1e9)}"
                          if rec.label else fmt_ns(value * 1e9)))
        return {
            'shot': shot, 'phase': rec.phase, 'macro': rec.macro,
            'label': rec.label, 'value': value, 'value_str': vstr,
            'src_line': src.line if src else None,
            'src_lines': list(src.lines) if src else [],
            'qua_line': qmap.get(rec.index), 'note': rec.note,
            'data_key': rec.data_key,
        }

    # ---- main ------------------------------------------------------------
    def build(self):
        from waxx.util.seqview.bundle import Bundle, empty_meta

        samples = self.job.get_simulated_samples()
        report = self.job.get_simulated_waveform_report()
        con = list(samples.keys())[0] if hasattr(samples, 'keys') else 'con1'
        csamp = samples[con]

        qmap, qerr = qua_line_map(self.log, self.qua_sim)
        if qerr:
            self.warn(qerr, 'info')

        self._make_lanes(csamp)
        items = expand_execution(self.log, self.n_shots)
        clocks = self._match(items, report, qmap)
        self._steps(items, clocks, qmap)
        shots, framing = self._shots(items, clocks)
        self._events(items, clocks, report, qmap)
        self._check_edges()

        meta = empty_meta(self.info.get('title', 'OPX simulation'))
        meta['subtitle'] = self.info.get('subtitle', '')
        meta['t_end_ns'] = self.duration_ns
        meta['dt_ns'] = 1.0
        meta['lanes'] = self.lanes
        meta['pulses'] = self.pulses
        meta['events'] = self.events
        meta['shots'] = shots
        meta['framing'] = framing
        meta['sources'] = self._sources()
        meta['params'] = self._params()
        meta['warnings'] = self.warnings
        meta['info'] = self.info
        return Bundle(meta, self.arrays).validate()

    # ---- lanes -----------------------------------------------------------
    def _make_lanes(self, csamp):
        cmap = self.cmap
        # semantic group
        self._add_lane('steps', 'sequence steps', 'semantic', 'semantic',
                       COLORS['steps'],
                       note='one bar per macro call; grey = handshake framing')
        for role, spec in cmap.channels.items():
            self._add_lane(f'light:{role}', f'{role} light ON', 'semantic',
                           'semantic', self._role_color(role), role=role,
                           element=spec.switch_element,
                           note=f"'pass' windows on {spec.switch_element}: "
                                f"ARTIQ RF reaches the {role} switch AOM")
        for role, spec in cmap.channels.items():
            if spec.measure_element:
                self._add_lane(f'adc:{role}', f'{role} ADC acquire',
                               'adc', 'semantic', COLORS['adc'], role=role,
                               element=spec.measure_element,
                               note=f'integration windows on '
                                    f'{spec.measure_element} (ADC in '
                                    f'{self.cfg.adc_port(spec.measure_element)})')
        self._add_lane('handback', 'hand-back to ARTIQ', 'semantic',
                       'semantic', COLORS['handback'],
                       element=cmap.handback_element,
                       note='trigger pulse on '
                            f'{cmap.handback_element}; ARTIQ resumes its '
                            f'timeline on this edge')

        # physical group: digital ports in port order
        el_by_dport, el_by_aport = {}, {}
        for el in self.cfg.elements:
            dp = self.cfg.digital_port(el)
            if dp is not None:
                el_by_dport.setdefault(dp, []).append(el)
            ap = self.cfg.analog_port(el)
            if ap is not None:
                el_by_aport.setdefault(ap, []).append(el)

        for key in sorted(csamp.digital.keys(), key=_port_sort):
            port = key.split('-')[-1]
            els = el_by_dport.get(port, [])
            el = els[0] if els else None
            role, what = self._role_of_element(el) if el else (None, None)
            arr = np.asarray(csamp.digital[key])
            from waxx.util.seqview.bundle import edges_from_samples
            level0, idx = edges_from_samples(arr)
            akey = f'edges:D{port}'
            self.arrays[akey] = idx.astype(np.float64)   # 1 ns per sample
            if what == 'switch':
                high, low = 'BLOCK', 'pass'
                note = (f'HIGH = ARTIQ RF to the {role} switch AOM blocked '
                        f'(light off); LOW = RF passes')
                color = _desaturate(self._role_color(role))
            elif what == 'handback':
                high, low, note = 'TRIG', '', 'hand-back trigger line'
                color = _desaturate(COLORS['handback'])
            elif what == 'measure':
                high, low = 'ACQ', ''
                note = 'ADC-window scope marker (not a beam switch)'
                color = _desaturate(COLORS['adc'])
            else:
                high, low, note, color = '1', '0', '', '#9a9a9a'
            self._add_lane(f'D{port}', f'D{port} {el or ""}'.strip(),
                           'digital', 'physical', color, element=el,
                           port=port, role=role, note=note, high_label=high,
                           low_label=low, edges=akey, level0=level0,
                           height=0.6)

        for key in sorted(csamp.analog.keys(), key=_port_sort):
            port = key.split('-')[-1]
            els = el_by_aport.get(port, [])
            el = els[0] if els else None
            role, _what = self._role_of_element(el) if el else (None, None)
            arr = np.asarray(csamp.analog[key])
            if np.iscomplexobj(arr):
                arr = np.real(arr)
            akey = f'analog:A{port}'
            self.arrays[akey] = arr.astype(np.float32)
            f = self.cfg.intermediate_frequency(el) if el else None
            a = self.cfg.analog_amplitude(el) if el else None
            desc = []
            if f is not None:
                desc.append(f'{float(f) / 1e6:g} MHz')
            if a is not None:
                desc.append(f'{a:g} V')
            self._add_lane(f'A{port}', f'A{port} {el or ""}'.strip(),
                           'analog', 'physical', COLORS['analog'],
                           element=el, port=port, role=role,
                           note=('sticky drive: ' + ' · '.join(desc)
                                 if desc else ''),
                           samples=akey, height=0.9)

    # ---- matching --------------------------------------------------------
    def _match(self, items, report, qmap):
        """Walk the execution stream against the report. Returns the
        per-item (t0, t1) timeline clocks and fills the pulse list."""
        cfg = self.cfg
        # per element, in time order. A measurement shows up twice in the
        # report (its analog pulse and its digital marker): keep the
        # digital one, drop an analog entry at the same timestamp.
        rep_by_el = defaultdict(list)
        for wf in report.digital_waveforms:
            rep_by_el[wf.element].append(wf)
        for wf in report.analog_waveforms:
            # the QOP lists a measurement's digital marker a few ns before
            # its analog pulse: same element, same name, near-equal time
            if any(abs(w.timestamp - wf.timestamp) <= 16
                   and _strip_origin(w.pulse_name) == _strip_origin(wf.pulse_name)
                   for w in rep_by_el.get(wf.element, [])):
                continue
            rep_by_el[wf.element].append(wf)
        for el in rep_by_el:
            rep_by_el[el].sort(key=lambda w: w.timestamp)
        adc_by_el = defaultdict(list)
        for acq in report.adc_acquisitions:
            adc_by_el[acq.element].append(acq)
        for el in adc_by_el:
            adc_by_el[el].sort(key=lambda a: a.start_time)

        cursor_rep = defaultdict(int)     # element -> next report index
        cursor_adc = defaultdict(int)
        el_clock = defaultdict(float)     # element -> its own timeline (ns)
        clocks = {}                       # item idx -> (t0, t1, matched)
        n_missing, first_missing_t = 0, None
        mismatch_reported = False

        def all_elements():
            # a global align() syncs every element of the config, touched
            # or not (the hand-back element sees its first play late)
            els = list(cfg.elements)
            return els + [e for e in el_clock if e not in els]

        for i, (rec, shot) in enumerate(items):
            el = rec.element
            kind = rec.kind
            prov = self._prov(rec, shot, qmap)
            if kind == 'align':
                els = rec.extra.get('elements') or all_elements()
                t = max([el_clock[e] for e in els] + [0.])
                for e in els:
                    el_clock[e] = t
                clocks[i] = (t, t, True)
                continue
            if kind == 'wait':
                els = rec.extra.get('elements') or [el]
                d = rec.duration_on(shot)
                d_ns = (d if d is not None else 0) * CLOCK_NS
                t0 = el_clock[els[0]]
                for e in els:
                    el_clock[e] = el_clock[e] + d_ns
                clocks[i] = (t0, t0 + d_ns, True)
                continue
            if kind in ('play', 'measure'):
                want = cfg.pulse_name(el, rec.op)
                reps = rep_by_el.get(el, [])
                j = cursor_rep[el]
                wf = reps[j] if j < len(reps) else None
                if wf is not None and _names_match(wf, rec, want):
                    cursor_rep[el] = j + 1
                    t0, t1 = float(wf.timestamp), float(wf.ends_at)
                    el_clock[el] = t1
                    clocks[i] = (t0, t1, True)
                    self._pulse_from_wf(rec, shot, wf, prov)
                    if kind == 'measure':
                        acqs = adc_by_el.get(el, [])
                        k = cursor_adc[el]
                        if k < len(acqs):
                            cursor_adc[el] = k + 1
                            self._adc_pulse(rec, shot, acqs[k], prov)
                        else:
                            self.warn(f"no ADC acquisition reported for "
                                      f"{rec.data_key or el} (shot {shot})")
                else:
                    # expected but not in the report: the window ended, or
                    # the report disagrees with the program
                    d = rec.duration_on(shot)
                    length = (d * CLOCK_NS if d is not None
                              else (cfg.pulse_length(el, rec.op) or 0))
                    t0 = el_clock[el]
                    el_clock[el] = t0 + length
                    clocks[i] = (t0, t0 + length, False)
                    n_missing += 1
                    if first_missing_t is None:
                        first_missing_t = t0
                    if wf is not None and not mismatch_reported:
                        mismatch_reported = True
                        self.warn(
                            f"report/program disagreement on {el}: expected "
                            f"{rec.op!r} ({want!r}) next but the simulator "
                            f"reported {_strip_origin(wf.pulse_name)!r} at "
                            f"{fmt_ns(wf.timestamp)}", 'error')
                    self._pulse_from_wf(rec, shot, None, prov, t0=t0,
                                        t1=t0 + length)
                continue
            if kind == 'ramp_to_zero':
                t0 = el_clock[el]
                clocks[i] = (t0, t0, True)
                continue
            # point ops (events) and save: no time
            t = el_clock[el] if el is not None else max(
                [el_clock[e] for e in all_elements()] + [0.])
            clocks[i] = (t, t, True)

        # leftovers the program never asked for
        for el, reps in rep_by_el.items():
            extra = reps[cursor_rep[el]:]
            if extra:
                self.warn(f"{len(extra)} reported pulse(s) on {el} have no "
                          f"counterpart in the program trace (first at "
                          f"{fmt_ns(extra[0].timestamp)})", 'error')
                for wf in extra:
                    self._orphan_pulse(wf)
        if n_missing:
            level = 'error'
            if first_missing_t is not None and first_missing_t >= self.duration_ns - 1:
                text = (f"simulation window ({fmt_ns(self.duration_ns)}) ended "
                        f"before the program did: {n_missing} pulse(s) not "
                        f"simulated (first expected at "
                        f"{fmt_ns(first_missing_t)}). Increase duration.")
            else:
                text = (f"{n_missing} pulse(s) the program expected were not "
                        f"reported by the simulator (first expected at "
                        f"{fmt_ns(first_missing_t)})")
            self.warn(text, level)
            self._not_simulated_from = first_missing_t
        else:
            self._not_simulated_from = None
        return clocks

    def _pulse_from_wf(self, rec, shot, wf, prov, t0=None, t1=None):
        """One pulse on the physical lane of the element, and, for the
        semantic roles, on the light / hand-back lane."""
        cfg = self.cfg
        el = rec.element
        role, what = self._role_of_element(el)
        if wf is not None:
            t0, t1 = float(wf.timestamp), float(wf.ends_at)
            pulse_name = _strip_origin(wf.pulse_name)
        else:
            pulse_name = cfg.pulse_name(el, rec.op)
        actual = t1 - t0
        requested = None
        rounded = False
        if rec.values is not None and rec.duration_cc is not None:
            v = rec.value_on(shot if shot is not None else 0)
            requested = v * 1e9
            rounded = abs(requested - actual) > 0.5
        elif rec.duration_cc is not None:
            d = rec.duration_on(shot if shot is not None else 0)
            requested = d * CLOCK_NS
        not_sim = wf is None
        base = dict(prov, element=el, op=rec.op, pulse_name=pulse_name,
                    t0=t0, t1=t1, requested_ns=requested, actual_ns=actual,
                    rounded=rounded)
        if not_sim:
            base['note'] = (base['note'] + ' | NOT SIMULATED (outside the '
                            'window or missing from the report)').strip(' |')
            base['color'] = '#ff5555'

        # physical lane
        dport = cfg.digital_port(el)
        aport = cfg.analog_port(el)
        lane = None
        if dport is not None and f'D{dport}' in self._lane_ids:
            lane = f'D{dport}'
        elif aport is not None and f'A{aport}' in self._lane_ids:
            lane = f'A{aport}'
        if lane is not None:
            text = rec.op or pulse_name
            self._add_pulse(lane, kind=('latch' if rec.macro == 'latch'
                                        else 'play'),
                            text=text, **base)

        # semantic lanes
        if what == 'switch':
            spec = self.cmap.spec(role)
            if rec.op == spec.pass_op and rec.macro != 'handback':
                # exposure: from the pass start to the re-block that follows
                # on this element (matched separately; use the pass length,
                # the block play is back-to-back)
                if rec.duration_cc is None:
                    return   # release to pass (no duration): not an exposure
                text = (f"{rec.label or rec.macro} · {fmt_ns(actual)}"
                        if rec.label else f"{rec.macro} · {fmt_ns(actual)}")
                self._add_pulse(f'light:{role}', kind='exposure', text=text,
                                **base)
        elif what == 'handback':
            self._add_pulse('handback', kind='trigger',
                            text=f'hand-back · {fmt_ns(actual)}', **base)

    def _adc_pulse(self, rec, shot, acq, prov):
        role, _ = self._role_of_element(rec.element)
        lane = f'adc:{role}'
        if lane not in self._lane_ids:
            return
        t0, t1 = float(acq.start_time), float(acq.end_time)
        # the step bar of this measure call extends over the ADC window
        self._adc_spans.setdefault((shot, rec.call), []).append((t0, t1))
        dark = bool(rec.extra.get('dark', False))
        n = rec.note
        which = rec.data_key
        m = re.search(r'\[(\d+)\]', n)
        if m:
            which = f"{rec.data_key}[{m.group(1)}]"
        text = f"{which} · {fmt_ns(t1 - t0)}" + (' · dark' if dark else '')
        self._add_pulse(lane, kind='adc', element=rec.element,
                        op=rec.op, pulse_name=self.cfg.pulse_name(
                            rec.element, rec.op),
                        t0=t0, t1=t1, actual_ns=t1 - t0,
                        requested_ns=self.cfg.pulse_length(rec.element, rec.op),
                        text=text, **prov)

    def _orphan_pulse(self, wf):
        el = wf.element
        dport = self.cfg.digital_port(el)
        aport = self.cfg.analog_port(el)
        lane = (f'D{dport}' if dport is not None and f'D{dport}' in self._lane_ids
                else (f'A{aport}' if aport is not None else None))
        if lane is None:
            return
        self._add_pulse(lane, element=el, pulse_name=_strip_origin(wf.pulse_name),
                        t0=float(wf.timestamp), t1=float(wf.ends_at),
                        actual_ns=float(wf.length), text='?',
                        note='reported by the simulator but not in the '
                             'program trace', color='#ff5555')

    # ---- steps lane --------------------------------------------------------
    def _steps(self, items, clocks, qmap):
        """One bar per macro call group per shot."""
        groups = []   # (key, [item indices])
        cur_key, cur = None, []
        for i, (rec, shot) in enumerate(items):
            key = (shot, rec.call)
            if key != cur_key:
                if cur:
                    groups.append((cur_key, cur))
                cur_key, cur = key, []
            cur.append(i)
        if cur:
            groups.append((cur_key, cur))

        for (shot, call), idxs in groups:
            recs = [items[i][0] for i in idxs]
            timed = [clocks[i] for i in idxs if i in clocks]
            if not timed:
                continue
            t0 = min(c[0] for c in timed)
            t1 = max(c[1] for c in timed)
            for a, b in self._adc_spans.get((shot, call), []):
                t1 = max(t1, b)
            matched = all(c[2] for c in timed)
            head = recs[0]
            macro = self.log.calls.get(call, head.macro) or head.macro
            # the record carrying the parameter, if any
            lab = next((r for r in recs if r.label), None)
            prov = self._prov(lab or head, shot, qmap)
            phase = head.phase
            if macro in ('handoff', 'shot_end', 'latch', 'epilogue'):
                phase = PHASE_HANDSHAKE if macro in ('handoff', 'shot_end') \
                    else head.phase
            if macro == 'handback' and head.phase == PHASE_HANDSHAKE:
                phase = PHASE_HANDSHAKE
            dur = t1 - t0
            if macro == 'wait_s':
                text = f"wait · {fmt_ns(dur)}"
                kind = 'wait'
            elif macro == 'handoff':
                text = f"handoff: block + settle · {fmt_ns(dur)}"
                kind = 'wait'
            elif macro == 'handback':
                text = f"hand-back + overlap · {fmt_ns(dur)}"
                kind = 'trigger'
            elif macro == 'measure':
                text = f"measure {head.data_key} · {fmt_ns(dur)}"
                kind = 'adc'
            elif macro == 'latch':
                text = 'latch analog drives'
                kind = 'latch'
            elif macro == 'epilogue':
                text = 'ramp analog drives to zero'
                kind = 'latch'
            elif macro == 'shot_end':
                continue
            elif dur <= 0:
                text = macro
                kind = 'play'
            else:
                text = f"{macro} · {fmt_ns(dur)}"
                kind = 'exposure'
            color = (COLORS['framing'] if phase == PHASE_HANDSHAKE
                     or macro in ('latch', 'epilogue')
                     else (COLORS['wait'] if macro == 'wait_s'
                           else COLORS['steps']))
            note = head.note if len(recs) == 1 else '; '.join(
                dict.fromkeys(r.note for r in recs if r.note))
            if not matched:
                note = (note + ' | NOT SIMULATED').strip(' |')
                color = '#ff5555'
            if macro == 'wait_s' and lab is not None:
                d = lab.duration_on(shot if shot is not None else 0)
                if d is not None:
                    prov['value_str'] = prov['value_str'] or fmt_ns(d * CLOCK_NS)
            self._add_pulse('steps', kind=kind, text=text, t0=t0, t1=t1,
                            color=color, **dict(prov, phase=phase,
                                                macro=macro, note=note))

    # ---- shots and framing --------------------------------------------------
    def _shots(self, items, clocks):
        shots, framing = [], []
        by_shot = defaultdict(list)
        for i, (rec, shot) in enumerate(items):
            if shot is not None and i in clocks:
                by_shot[shot].append(i)
        names = sorted(self.tables.accessed)
        for s in range(self.n_shots):
            idxs = by_shot.get(s, [])
            if not idxs:
                continue
            t0 = min(clocks[i][0] for i in idxs)
            t1 = max(clocks[i][1] for i in idxs)
            simulated = any(clocks[i][2] for i in idxs)
            params = {}
            for name in names:
                if self.tables.has(name):
                    params[name] = fmt_param(name, self.tables.column(name)[s])
            label = f"shot {s}"
            if params:
                label += '  ' + '  '.join(f"{k} = {v}" for k, v in params.items())
            shots.append({'index': s, 't0': t0, 't1': min(t1, self.duration_ns),
                          'label': label, 'params': params,
                          'simulated': simulated})
            # framing bands: handoff group and hand-back group
            hs = [i for i in idxs if items[i][0].phase == PHASE_HANDSHAKE
                  or items[i][0].macro == 'handback']
            hand_in = [i for i in hs if items[i][0].macro == 'handoff']
            hand_out = [i for i in hs if items[i][0].macro == 'handback']
            if hand_in:
                a = min(clocks[i][0] for i in hand_in)
                b = max(clocks[i][1] for i in hand_in)
                framing.append({'t0': a, 't1': b, 'shot': s, 'kind': 'handoff',
                                'label': 'handoff: RF blocked, settle'})
            if hand_out:
                a = min(clocks[i][0] for i in hand_out)
                b = max(clocks[i][1] for i in hand_out)
                framing.append({'t0': a, 't1': b, 'shot': s, 'kind': 'handback',
                                'label': 'hand-back: trigger, overlap, release'})
        if self._not_simulated_from is not None:
            t0 = min(self._not_simulated_from, self.duration_ns)
            framing.append({'t0': t0, 't1': self.duration_ns, 'shot': None,
                            'kind': 'not_simulated',
                            'label': 'program continues beyond the '
                                     'simulated window'})
        return shots, framing

    # ---- events ------------------------------------------------------------
    def _events(self, items, clocks, report, qmap):
        cfg = self.cfg
        # simulator-reported events (phase resets), consumed in order per element
        rep_ev = defaultdict(list)
        for ev in report.events:
            rep_ev[ev.element].append(ev)
        for el in rep_ev:
            rep_ev[el].sort(key=lambda e: e.timestamp)
        used = defaultdict(int)

        def lane_for(el):
            ap = cfg.analog_port(el)
            if ap is not None and f'A{ap}' in self._lane_ids:
                return f'A{ap}'
            dp = cfg.digital_port(el)
            if dp is not None and f'D{dp}' in self._lane_ids:
                return f'D{dp}'
            return None

        for i, (rec, shot) in enumerate(items):
            if rec.kind not in EVENT_KINDS:
                continue
            lane = lane_for(rec.element)
            if lane is None:
                continue
            prov = self._prov(rec, shot, qmap)
            t = clocks[i][0]
            approx = True
            detail = rec.note
            if rec.kind == 'reset_if_phase':
                label = 'phase reset'
                evs = rep_ev.get(rec.element, [])
                k = used[rec.element]
                match = next((e for e in evs[k:] if e.name == 'phase_reset'), None)
                if match is not None:
                    used[rec.element] = evs.index(match) + 1
                    t, approx = float(match.timestamp), False
                    detail = 'IF phase reset (reported by the simulator)'
            elif rec.kind == 'update_frequency':
                f = rec.extra.get('frequency_hz')
                fv = None
                if f is not None:
                    fa = np.atleast_1d(f)
                    fv = float(fa[shot] if fa.size > 1 and shot is not None
                               else fa[0])
                label = (f"IF → {fv / 1e6:g} MHz" if fv is not None
                         else 'IF change')
                detail = ('frequency update; time inferred from the program '
                          '(the simulator does not report it)')
            elif rec.kind == 'frame_rotation_2pi':
                tv = rec.extra.get('turns')
                tt = None
                if tv is not None:
                    ta = np.atleast_1d(tv)
                    tt = float(ta[shot] if ta.size > 1 and shot is not None
                               else ta[0])
                label = (f"frame +{tt:g}·2π" if tt is not None
                         else 'frame rotation')
                detail = ('frame rotation; time inferred from the program')
            elif rec.kind == 'reset_frame':
                label = 'frame reset'
                detail = 'frame reset; time inferred from the program'
            else:
                label = rec.kind
            self._add_event(lane, t, rec.kind, label, detail,
                            src_line=prov['src_line'],
                            src_lines=prov['src_lines'],
                            qua_line=prov['qua_line'], approx=approx,
                            shot=shot)
        # reported events the program did not ask for
        for el, evs in rep_ev.items():
            for e in evs[used[el]:]:
                lane = lane_for(el)
                if lane is None:
                    continue
                self._add_event(lane, e.timestamp, e.name, e.name,
                                'reported by the simulator', approx=False)
        # analog state changes between consecutive played waveforms
        by_el = defaultdict(list)
        for wf in report.analog_waveforms:
            by_el[wf.element].append(wf)
        for el, wfs in by_el.items():
            wfs.sort(key=lambda w: w.timestamp)
            lane = lane_for(el)
            if lane is None:
                continue
            for a, b in zip(wfs, wfs[1:]):
                changes = []
                if a.current_intermediate_frequency != b.current_intermediate_frequency:
                    changes.append(
                        f"IF {a.current_intermediate_frequency / 1e6:g} → "
                        f"{b.current_intermediate_frequency / 1e6:g} MHz")
                if list(a.current_amp_elements) != list(b.current_amp_elements):
                    changes.append(f"amp {a.current_amp_elements} → "
                                   f"{b.current_amp_elements}")
                if a.current_phase != b.current_phase:
                    changes.append(f"phase {a.current_phase:g} → "
                                   f"{b.current_phase:g}")
                if list(a.current_frame) != list(b.current_frame):
                    changes.append(f"frame {a.current_frame} → "
                                   f"{b.current_frame}")
                if changes:
                    self._add_event(lane, b.timestamp, 'analog_change',
                                    '; '.join(changes),
                                    'analog state differs from the previous '
                                    'pulse on this element (waveform report)',
                                    approx=False)

    # ---- cross-check: report vs sample edges ---------------------------------
    def _check_edges(self):
        """Every exposure pulse should be bracketed by a falling and a rising
        edge on its switch port in the samples."""
        for lane in self.lanes:
            if lane['kind'] != 'digital' or lane['role'] is None:
                continue
            role = lane['role']
            edges = self.arrays.get(lane['edges'])
            if edges is None:
                continue
            light = self._lane_ids.get(f'light:{role}')
            if light is None:
                continue
            bad = 0
            for pid in light['pulses']:
                p = self.pulses[pid]
                if p['truncated'] or p['color'] == '#ff5555':
                    continue
                for t in (p['t0'], p['t1']):
                    if t >= self.duration_ns:
                        continue
                    k = np.searchsorted(edges, t - 1.5)
                    if not (k < edges.size and abs(edges[k] - t) <= 1.5):
                        bad += 1
            if bad:
                self.warn(f"{bad} exposure edge(s) on {lane['id']} have no "
                          f"matching level change in the simulated samples "
                          f"(report and samples disagree)", 'error')

    # ---- sources / params ----------------------------------------------------
    def _sources(self):
        log = self.log
        seq_name = getattr(self.sequence, 'name', 'sequence')
        src = {}
        if log.source_text:
            path = log.source_path or ''
            src['seq'] = {'title': os.path.basename(path) or seq_name,
                          'path': path, 'text': log.source_text,
                          'first_line': int(log.source_first_line),
                          'language': 'python'}
        if self.qua_sim:
            src['qua'] = {'title': 'QUA (simulated)', 'path': '',
                          'text': self.qua_sim, 'first_line': 1,
                          'language': 'python',
                          'note': 'the variant sent to the simulator: '
                                  'triggers skipped, scoped to the simulated '
                                  'shots'}
        if self.qua_real:
            src['qua_real'] = {'title': 'QUA (run)', 'path': '',
                               'text': self.qua_real, 'first_line': 1,
                               'language': 'python',
                               'note': 'the real triggered program a run '
                                       'saves as provenance'}
        try:
            cfg_text = pprint.pformat(self.config, width=88, sort_dicts=False)
        except Exception:
            cfg_text = repr(self.config)
        src['config'] = {'title': 'OPX config', 'path': '', 'text': cfg_text,
                         'first_line': 1, 'language': 'python'}
        return src

    def _params(self):
        names = sorted(self.tables.accessed)
        cols, disp = {}, {}
        for n in names:
            if self.tables.has(n):
                c = self.tables.column(n)
                cols[n] = [float(v) for v in c]
                disp[n] = [fmt_param(n, v) for v in c]
        return {'names': names, 'columns': cols, 'display': disp}


def _names_match(wf, rec, pulse_name):
    """The QOP reports a played pulse under its *operation* name (the
    key in the element's operations map); older/offline reports use the
    config pulse name; a measurement is reported as '@MeasPulseInternalN'.
    Accept any of them."""
    name = _strip_origin(wf.pulse_name)
    if name == rec.op or (pulse_name is not None and name == pulse_name):
        return True
    if rec.kind == 'measure' and name.startswith('@Meas'):
        return True
    return False


def _port_sort(key):
    try:
        return tuple(int(x) for x in str(key).split('-'))
    except ValueError:
        return (999, str(key))


def _desaturate(hexcolor, factor=0.45):
    h = hexcolor.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    grey = 0.3 * r + 0.59 * g + 0.11 * b
    r, g, b = (int(grey + (c - grey) * factor) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def build_bundle(job, builder, cmap, config, duration_ns, qua_sim='',
                 qua_real='', info=None, sequence=None):
    """The seqview bundle for one simulation (see BundleBuilder)."""
    return BundleBuilder(job, builder, cmap, config, duration_ns,
                         qua_sim=qua_sim, qua_real=qua_real, info=info,
                         sequence=sequence).build()


def show_bundle(bundle, inline=False, reuse=True, name=None):
    """Open (or update) the pulse viewer on a bundle. Returns the bundle
    path (subprocess mode) or the window (inline mode)."""
    from waxx.util.seqview import show
    return show(bundle, inline=inline, reuse=reuse, name=name)
