"""OPXShotContext -- what a sequence author sees as ``ctx``.

All methods here are trace-time: they expand into QUA inside the builder's
shot loop (which is traced once; the OPX executes it once per shot). Times
are SI seconds everywhere a sequence writes them; conversion to clock cycles
happens host-side, per shot, when the value tables are built.

``ctx.p.<param>`` is a ParamRef: a fixed parameter bakes in as a constant,
a scanned (or scanned-derived) parameter becomes a QUA array lookup indexed
by the shot counter -- one sequence works unchanged either way, like
scan_kernel on the ARTIQ side. Arithmetic on a ParamRef (ctx.p.t_pi / 2,
np.maximum(...)) is worked out per shot on the host and resolves the same
way; what it cannot do is collapse to one number (float(), `if`) -- see
ParamRef, and ctx.const() for run-level constants.

Real-time work on the OPX (a measurement feeding the next pulse) goes
through the raw-QUA layer: ``ctx.qua`` is the qm.qua module, ``ctx.shot``
the loop counter, and every duration/frequency macro accepts a QUA int
expression in place of a ParamRef (then no host checks apply -- the value
is whatever the OPX computes). ``ctx.shot_array`` ships a host-drawn
per-shot table as ONE flat QUA array, ``ctx.for_range`` is a QUA loop whose
saves are counted for validation, ``ctx.save`` streams any QUA scalar into
a declared key, and ``ctx.host_data`` records what the host handed the OPX
so the run file carries both sides.

Generic (future waxx.control.opx): no kexp imports; qm imported inside
methods only (ctx.qua imports it on first access).
"""

import contextlib
import sys
from typing import Generic, TypeVar, cast

import numpy as np

from kexp.control.opx.params_bridge import (ParamRef, ParamsProxy, ShotTables,
                                            as_host_scalar)
from kexp.control.opx.channels import ChannelMap
from kexp.control.opx.sequence import Stream, _as_dtype
from kexp.control.opx.units import (s_to_cc, hz_to_int, MIN_PULSE_CC,
                                    QUA_FIXED_LIMIT)
from kexp.control.opx.trace_log import OpLog, PHASE_BODY

# The lab's params class, for editors only: annotating a sequence with
# OPXShotContext[ExptParams] makes ctx.p.<name> complete against the real
# parameter names, and the float the editor shows is how a ParamRef behaves
# under arithmetic (column-wise, per shot, on the host). What the static
# type cannot say: at runtime ctx.p hands out ParamRefs, which never
# collapse to one number -- float()/int()/`if` raise (see ParamRef).
P = TypeVar('P')

# Value saved into a timestamp stream on a shot where the timestamped
# play/measure was skipped by its per-shot duration guard (d < 16 ns), so
# the stream keeps exactly one entry per declared save and the buffers
# stay aligned. Real OPX timestamps are >= 0.
TIMESTAMP_SKIPPED = -1

# Linearity tolerance for set_transition_offset's numeric slope (relative,
# checked over +-2 MHz around the run's transition).
_SLOPE_REL_TOL = 1.e-9
_SLOPE_CHECK_HZ = (-2.e6, -1.e6, 1.e6, 2.e6)


def is_qua_expr(x) -> bool:
    """True for a QUA scalar expression (variable, array cell, arithmetic,
    library-function output). qm-free: a QUA expression can only exist once
    qm.qua is imported, so an un-imported qm means False."""
    mod = sys.modules.get('qm.qua._expressions')
    if mod is None:
        return False
    return isinstance(x, mod.QuaScalarExpression)


def _fmt_shape(shape):
    return '(' + ', '.join(str(int(n)) for n in shape) + ')'


class ShotArray:
    """A host-drawn per-shot table shipped to the OPX as one flat QUA array
    (see OPXShotContext.shot_array). ``at(i)`` is the QUA cell for the
    current shot: ``qua_array[shot * M + i]``.

    values: the host copy, shape (n_shots,) or (n_shots, M), read-only.
    """

    def __init__(self, ctx, key, values, dtype, qua_array):
        self._ctx = ctx
        self.key = key
        self.dtype = dtype
        v = np.asarray(values, dtype=float).copy()
        v.flags.writeable = False
        self.values = v
        self.M = int(v.shape[1]) if v.ndim == 2 else 1
        self._qua = qua_array

    @property
    def qua_array(self):
        """The declared flat QUA array itself (length n_shots * M)."""
        return self._qua

    @property
    def n_shots(self) -> int:
        return int(self.values.shape[0])

    def at(self, i=0):
        """QUA cell of entry i on the current shot. i: a Python int in
        [0, M), or a QUA int expression (a ctx.for_range loop variable) --
        no bounds check is possible then; QUA does none either."""
        shot = self._ctx._shot
        if is_qua_expr(i):
            if self.M == 1:
                return self._qua[shot + i]
            return self._qua[shot * self.M + i]
        if isinstance(i, (bool, np.bool_)) or not isinstance(i, (int, np.integer)):
            raise TypeError(
                f"[opx] shot_array {self.key!r}.at(i): i must be an int or "
                f"a QUA int expression, got {type(i).__name__}: {i!r}")
        i = int(i)
        if not 0 <= i < self.M:
            raise IndexError(
                f"[opx] shot_array {self.key!r}.at({i}): {i} is outside "
                f"[0, {self.M}) -- the table has {self.M} value(s) per shot.")
        if self.M == 1:
            return self._qua[shot]
        return self._qua[shot * self.M + i]

    def __repr__(self):
        d = 'int' if self.dtype is int else 'float'
        return (f"ShotArray({self.key!r}, {_fmt_shape(self.values.shape)}, "
                f"{d})")


class OPXShotContext(Generic[P]):

    p: P

    def __init__(self, channel_map: ChannelMap, tables: ShotTables,
                 sequence, shot_var, hold_cc, guarded_specs, log=None,
                 measurements=None, host_data=None):
        self.p = cast(P, ParamsProxy(tables))
        self._map = channel_map
        self._tables = tables
        self._sequence = sequence
        self._shot = shot_var
        self._hold_cc = int(hold_cc)
        self._guarded_specs = list(guarded_specs)

        # declared per-shot shapes: {key: Stream}. Given by the builder
        # (resolved against the live params); a bare context resolves what
        # it can from the sequence (callables then need params -> error).
        if measurements is None:
            resolve = getattr(sequence, 'resolve_measurements', None)
            measurements = resolve(None) if resolve is not None else {}
        if host_data is None:
            resolve = getattr(sequence, 'resolve_host_data', None)
            host_data = resolve(None) if resolve is not None else {}
        self._measurements = dict(measurements)
        self._host_data_specs = dict(host_data)

        self._qua_arrays = {}    # (tag, values) -> declared QUA array
        self._streams = {}       # data key -> declared output stream
        self._measure_vars = {}  # data key -> QUA fixed variable (measure)
        self._stream_roles = {}  # data key -> channel role (for V conversion)
        self._save_counts = {}   # data key -> saves traced per shot
        self._loop_stack = []    # ctx.for_range counts, innermost last
        self._shot_arrays = {}   # key -> host values (provenance)
        self._shot_arrays_qua = {}
        self._host_data_values = {}   # key -> (n_shots, *shape) host values
        self._handback_done = False
        # roles whose analog drive frequency the sequence changed: the
        # builder points them back at the run's transition after the body
        self._if_touched = set()

        # provenance: every emitted QUA statement, with the sequence source
        # line and the per-shot values behind it (read by the pulse viewer)
        self._log: OpLog = log if log is not None else OpLog(
            getattr(sequence, 'func', None), tables.n_shots)
        # (label, raw per-shot SI values, converted per-shot column) of the
        # most recent _resolve, so the macros can log what they resolved
        self._last_resolved = ('', None, None)

    @property
    def log(self) -> OpLog:
        return self._log

    # ------------------------------------------------------------------
    # raw-QUA layer
    # ------------------------------------------------------------------

    @property
    def qua(self):
        """The qm.qua module (imported on first access): declare, assign,
        Math, Cast, Util, if_/else_, ... for real-time work the macros do
        not cover. Statements written this way are not in the op log."""
        from qm import qua
        return qua

    @property
    def shot(self):
        """The QUA int loop variable of the builder's shot loop (0-based,
        execution order)."""
        return self._shot

    @property
    def n_shots(self) -> int:
        return int(self._tables.n_shots)

    def _loop_scale(self) -> int:
        n = 1
        for m in self._loop_stack:
            n *= int(m)
        return n

    def _count_save(self, key, n=1):
        self._save_counts[key] = (self._save_counts.get(key, 0)
                                  + int(n) * self._loop_scale())

    # ------------------------------------------------------------------
    # Parameter resolution (SI in, OPX units out)
    # ------------------------------------------------------------------

    def _check_ref(self, x):
        if x._tables is not self._tables:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: {x!r} belongs to "
                f"another run's shot tables -- a sequence must only use the "
                f"ctx.p it was called with.")

    @staticmethod
    def _check_finite(x, label, raw):
        col = np.atleast_1d(raw)
        bad = np.flatnonzero(~np.isfinite(col))
        if not bad.size:
            return
        where = ""
        if isinstance(x, ParamRef):
            shown = bad[:8].tolist() + (['...'] if bad.size > 8 else [])
            where = f" on {bad.size} shot(s) (execution-order index {shown})"
        raise ValueError(
            f"[opx] {label!r} is {col[bad[0]]}{where} -- NaN/inf cannot be "
            f"shipped to the OPX. A division by a parameter that is 0 on "
            f"some shot, or a derived parameter left unset?")

    @staticmethod
    def _check_int32(label, col):
        if np.any(np.abs(col) >= 2 ** 31):
            raise ValueError(
                f"[opx] {label!r} = {np.min(col)} .. {np.max(col)} does not "
                f"fit a 32-bit QUA int (durations of 8.6 s or more, "
                f"frequencies of 2.1 GHz or more). A seconds-vs-microseconds "
                f"slip?")

    @staticmethod
    def _check_fixed(label, col):
        if np.any((col < -QUA_FIXED_LIMIT) | (col >= QUA_FIXED_LIMIT)):
            raise ValueError(
                f"[opx] {label!r} = {np.min(col):g} .. {np.max(col):g} is "
                f"outside the QUA fixed-point range [-{QUA_FIXED_LIMIT:g}, "
                f"{QUA_FIXED_LIMIT:g}) that ctx.f() values must fit (an "
                f"amp() factor, for one, must be within [-2, 2)).")

    def _resolve(self, x, transform, tag, qua_dtype, what):
        """ParamRef or number -> baked constant or QUA array lookup.

        A constant and a per-shot column take the same path (transform,
        then range checks), so whether a value is valid never depends on
        whether it happens to be scanned this run. A QUA expression passes
        through untouched (the OPX computes it; no host checks apply) and
        _last_resolved records no column for it.
        """
        if is_qua_expr(x):
            self._last_resolved = ('<QUA expression>', None, None)
            return x
        if isinstance(x, ParamRef):
            self._check_ref(x)
            label, raw = x.label, x.column
        else:
            label, raw = what, as_host_scalar(x, what)
        self._check_finite(x, label, raw)
        col = np.atleast_1d(np.asarray(transform(raw)))
        if qua_dtype is int:
            self._check_int32(label, col)
        else:
            self._check_fixed(label, col)
        self._last_resolved = (label if isinstance(x, ParamRef) else '',
                               np.atleast_1d(np.asarray(raw, dtype=float)),
                               col)
        if np.all(col == col[0]):
            v = col[0]
            return int(v) if qua_dtype is int else float(v)
        from qm import qua
        values = ([int(v) for v in col] if qua_dtype is int
                  else [float(v) for v in col])
        # keyed by value: two spellings of the same per-shot column share
        # one QUA array, and distinct expressions can never collide
        cache_key = (tag, tuple(values))
        if cache_key not in self._qua_arrays:
            self._qua_arrays[cache_key] = qua.declare(
                int if qua_dtype is int else qua.fixed, value=values)
        return self._qua_arrays[cache_key][self._shot]

    def cc(self, t, key=''):
        """Seconds -> clock cycles: int if fixed, QUA int expression if it
        varies per shot. Use for play/wait durations. A QUA int expression
        is returned unchanged and taken to be clock cycles already (no
        host checks: the OPX computes it)."""
        name = t.label if isinstance(t, ParamRef) else key
        what = f"{key} duration" if key else "ctx.cc() argument"
        return self._resolve(t, lambda c: s_to_cc(c, key=name), 'cc', int,
                             what)

    def hz(self, f):
        """Hz -> integer Hz (for update_frequency). A QUA int expression
        passes through (integer Hz already)."""
        return self._resolve(f, hz_to_int, 'hz', int, 'ctx.hz() argument')

    def f(self, x):
        """Plain float (e.g. an amp() scaling factor): float if fixed, QUA
        fixed expression if it varies per shot. Must fit QUA fixed, [-8, 8).
        A QUA fixed expression passes through."""
        return self._resolve(x, lambda c: np.asarray(c, dtype=float),
                             'f', float, 'ctx.f() argument')

    def const(self, x) -> float:
        """A run-level constant as a Python float: a number, or a ctx.p
        parameter whose value is the same on every shot of this run.

        For trace-time decisions the program is *built* with -- a loop
        count (``for _ in range(int(ctx.const(ctx.p.N_pulses)))``), a
        which-branch toggle -- as opposed to values the OPX reads per shot.
        A parameter that varies per shot is refused, on purpose: the body
        is traced once, so it could only ever see one of the values, and
        every shot would silently get that one. Per-shot control flow on
        the OPX goes through the raw-QUA layer (ctx.qua, ctx.for_range,
        QUA expressions in the macros), never through a Python `if`.
        """
        if is_qua_expr(x):
            raise TypeError(
                "[opx] ctx.const() of a QUA expression: a QUA value only "
                "exists on the OPX at run time, it cannot become a host "
                "constant the program is built with.")
        if not isinstance(x, ParamRef):
            return as_host_scalar(x, 'ctx.const() argument')
        self._check_ref(x)
        c = x.column
        if not x.is_constant:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: "
                f"ctx.const({x.label!r}) but it varies per shot "
                f"({np.min(c):g} .. {np.max(c):g}) -- it is scanned, or "
                f"derived from a scanned parameter. ctx.const gives one "
                f"number the whole program is built with; a per-shot value "
                f"must reach the OPX through a ctx method (or "
                f"ctx.cc/ctx.hz/ctx.f).")
        return float(c[0])

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _check_open(self, what):
        if self._handback_done:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: {what} after "
                f"handback_to_artiq() -- ARTIQ owns the beams again at the "
                f"hand-back, so nothing may run on them afterwards.")

    def _claimed_spec(self, role):
        if role not in self._sequence.claims:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r} uses channel "
                f"{role!r} without claiming it -- add it to the sequence's "
                f"claims=(...) declaration.")
        return self._map.spec(role)

    def _all_elements(self):
        """Every QUA element the channel map names, in map order (the set a
        global wait must advance together)."""
        out = []
        for spec in self._map.channels.values():
            for el in (spec.switch_element, *spec.analog_elements,
                       spec.measure_element):
                if el and el not in out:
                    out.append(el)
        hb = self._map.handback_element
        if hb and hb not in out:
            out.append(hb)
        return out

    def _element_name(self, name):
        """A role name -> its switch element; an element name of the map ->
        itself; anything else is refused."""
        if name in self._map.channels:
            return self._map.spec(name).switch_element
        known = self._all_elements()
        if name in known:
            return name
        raise KeyError(
            f"[opx] {name!r} is neither a channel role "
            f"{sorted(self._map.channels)} nor an element of the map "
            f"{known}.")

    def elements(self, role) -> dict:
        """The QUA element names behind a role:
        dict(switch=..., analog=(...), measure=...)."""
        spec = self._map.spec(role)
        return dict(switch=spec.switch_element,
                    analog=tuple(spec.analog_elements),
                    measure=spec.measure_element)

    # ------------------------------------------------------------------
    # Exposure / pulses
    # ------------------------------------------------------------------

    def _timestamp_stream(self, key, what):
        """The declared int stream a play/measure timestamps into."""
        spec = self._measurements.get(key)
        if spec is None:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: {what} "
                f"timestamp_key={key!r} is not declared in its "
                f"measurements={{...}}.")
        if spec.dtype is not int:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: timestamp_key="
                f"{key!r} must be declared as an int stream "
                f"(Stream({spec.shape}, int)); OPX timestamps are clock "
                f"cycles, not volts.")
        if key in self._stream_roles:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: {key!r} is a "
                f"measure() key and cannot also take timestamps.")
        return self.stream(key)

    def _expose(self, role, t, phase_reset=False, timestamp_key=None,
                min_cc=None):
        """Open a channel's RF block for t seconds, then re-block.

        min_cc: for a QUA-expression duration only -- the caller's
        host-known lower bound on the duration in clock cycles (e.g.
        int(shot_array.values.min()) after converting to cycles). When it
        is >= MIN_PULSE_CC the per-shot ``if_(d >= 4)`` guard is omitted, so
        the pulse (and a phase-reset align in front of it) is emitted with
        no run-time branch. Ignored for host values, which are checked on
        the host anyway.

        The switch elements are sticky-digital: 'pass' holds the line low
        (RF through) until 'block' re-raises it, so the exposure is exactly
        the played 'pass' duration with no gap before the re-block.

        phase_reset: reset_if_phase on every analog drive of the role,
        then align(*drives, switch) immediately before the pass play -- the
        reset takes effect at that align, and the play is the next
        statement on the switch element, so the two-photon drive phase at
        pulse start is 0 (plus a hardware constant).

        timestamp_key: the pass play records its start time (clock cycles
        from program start) into that declared int stream -- one save on
        the key per pulse. A pulse skipped by its per-shot duration guard
        saves TIMESTAMP_SKIPPED (-1) instead, so the stream stays aligned.
        """
        from qm import qua
        self._check_open(f"pulse on {role!r}")
        spec = self._claimed_spec(role)
        self._log.new_call(f"{role}_pulse")
        macro = f"{role}_pulse"
        el = spec.switch_element
        if phase_reset and not spec.analog_elements:
            raise RuntimeError(
                f"[opx] channel {role!r} has no analog drives to phase-reset.")
        ts_stream = (self._timestamp_stream(timestamp_key, macro)
                     if timestamp_key is not None else None)
        d = self.cc(t, key=f"{role} pulse")
        label, raw, cc_col = self._last_resolved
        log = self._log

        def reset_then_align(executes=None):
            if not phase_reset:
                return
            for a in spec.analog_elements:
                log.record('reset_if_phase', a, macro=macro, executes=executes,
                           note='IF phase reset (takes effect at the align '
                                'that follows)')
                qua.reset_if_phase(a)
            els = [*spec.analog_elements, el]
            log.record('align', None, macro=macro, executes=executes,
                       elements=els,
                       note='drives + switch aligned: the phase reset lands '
                            'here and the pass play is next on the switch')
            qua.align(*els)

        def play_pass(executes=None):
            log.record('play', el, spec.pass_op, macro=macro, label=label,
                       values=raw, duration_cc=cc_col, executes=executes,
                       data_key=timestamp_key or '',
                       note=f'{role} exposure (RF passes)'
                            + (f'; start timestamped into {timestamp_key!r}'
                               if timestamp_key else ''))
            qua.play(spec.pass_op, el, duration=d, timestamp_stream=ts_stream)
            if timestamp_key is not None:
                self._count_save(timestamp_key)
            log.record('play', el, spec.block_op, macro=macro, label=label,
                       values=raw, executes=executes,
                       note=f'{role} re-blocked')
            qua.play(spec.block_op, el)

        if isinstance(d, (int, np.integer)):
            if d == 0:
                if timestamp_key is not None:
                    raise RuntimeError(
                        f"[opx] sequence {self._sequence.name!r}: "
                        f"{macro}({label or 'constant'}) is zero-length on "
                        f"every shot, so nothing is played and its "
                        f"timestamp_key={timestamp_key!r} could never be "
                        f"saved.")
                log.record('play', el, spec.pass_op, macro=macro,
                           label=label, values=raw, duration_cc=cc_col,
                           executes=np.zeros(self._tables.n_shots, bool),
                           note='zero-length pulse: nothing played')
                return          # a zero-length pulse is no pulse
            reset_then_align()
            play_pass()
            return

        if min_cc is not None and cc_col is None:
            # QUA-expression duration with a host-asserted lower bound: no
            # branch needed (the bound is the caller's responsibility; the
            # OPX plays whatever the expression evaluates to)
            if int(min_cc) < MIN_PULSE_CC:
                raise ValueError(
                    f"[opx] {macro}: min_cc={int(min_cc)} is below the "
                    f"{MIN_PULSE_CC}-cycle minimum; a duration that can be "
                    f"shorter than 16 ns needs the per-shot guard "
                    f"(leave min_cc=None).")
            reset_then_align()
            play_pass()
            return

        # duration varies per shot (host column) or is a QUA expression,
        # and may be zero on some shots (e.g. a Rabi scan from t = 0):
        # branch on the OPX
        runs = (cc_col >= MIN_PULSE_CC) if cc_col is not None else None
        log.record('if', None, macro=macro, label=label, values=raw,
                   duration_cc=cc_col, executes=runs,
                   note=f'skipped on shots where {label} < 16 ns')
        with qua.if_(d >= MIN_PULSE_CC):
            reset_then_align(executes=runs)
            play_pass(executes=runs)
        if timestamp_key is not None:
            with qua.else_():
                log.record('save', None, macro=macro, data_key=timestamp_key,
                           executes=(None if runs is None else ~runs),
                           note=f'timestamp placeholder {TIMESTAMP_SKIPPED}: '
                                f'the pulse was skipped on this shot')
                qua.save(TIMESTAMP_SKIPPED, ts_stream)

    def raman_pulse(self, t, phase_reset=False, timestamp_key=None,
                    min_cc=None):
        """Expose the atoms to the Raman beams for t seconds (SI; a ctx.p
        parameter scans per shot; a QUA int expression is clock cycles).

        phase_reset=True zeroes both Raman drives' IF phase at the pulse
        start (reset_if_phase x2, align(drives, switch), then the pass
        play with nothing in between). timestamp_key records the pulse
        start time into a declared int stream. min_cc (QUA durations
        only): a host-known lower bound in clock cycles that removes the
        per-shot zero-length guard. See _expose."""
        self._expose('raman', t, phase_reset=phase_reset,
                     timestamp_key=timestamp_key, min_cc=min_cc)

    def imaging_pulse(self, t, timestamp_key=None, min_cc=None):
        """Expose the atoms to the imaging beam for t seconds (SI; QUA int
        expression = clock cycles). timestamp_key / min_cc as for
        raman_pulse."""
        self._expose('imaging', t, timestamp_key=timestamp_key,
                     min_cc=min_cc)

    def raman_phase_reset(self):
        """Zero the relative phase of the Raman analog drives (no align:
        the reset takes effect at the next play/align on each drive).

        Not part of raman_pulse by default: reset_if_phase briefly occupies
        the analog cores, and a single-pulse experiment (Rabi) does not care
        about the two-photon phase origin. Multi-pulse sequences call this
        before their first pulse, or use raman_pulse(phase_reset=True).
        """
        from qm import qua
        self._check_open("raman_phase_reset")
        spec = self._claimed_spec('raman')
        self._log.new_call('raman_phase_reset')
        for el in spec.analog_elements:
            self._log.record('reset_if_phase', el, macro='raman_phase_reset',
                             note='IF phase reset to 0')
            qua.reset_if_phase(el)

    # ------------------------------------------------------------------
    # Analog drive control (frequency / frame) -- per-shot capable
    # ------------------------------------------------------------------

    def _analog_targets(self, role, which):
        spec = self._claimed_spec(role)
        els = list(spec.analog_elements)
        if not els:
            raise RuntimeError(
                f"[opx] channel {role!r} has no analog drive elements.")
        if which is None:
            return els
        if isinstance(which, str):
            if which not in els:
                raise RuntimeError(
                    f"[opx] {which!r} is not an analog element of "
                    f"{role!r} (has {els}).")
            return [which]
        return [els[int(which)]]

    def set_frequency(self, role, f, which=None, keep_phase=False):
        """Set the intermediate frequency of a channel's analog drive(s)
        to f Hz (SI; a ctx.p parameter scans per shot; a QUA int expression
        is integer Hz). `which` selects one drive by index or element name
        (default: every drive of the role). The change takes effect on the
        sticky drive immediately."""
        from qm import qua
        self._check_open("set_frequency")
        els = self._analog_targets(role, which)
        self._if_touched.add(role)
        self._log.new_call('set_frequency')
        v = self.hz(f)
        label, raw, col = self._last_resolved
        for el in els:
            self._log.record('update_frequency', el, macro='set_frequency',
                             label=label, values=raw, duration_cc=None,
                             note='IF change', frequency_hz=col)
            qua.update_frequency(el, v, keep_phase=keep_phase)

    def set_transition(self, role, f, keep_phase=False):
        """Point a channel's analog drives at a transition of f Hz (SI; a
        ctx.p parameter or expression scans per shot), e.g. a Ramsey
        detuning:

            ctx.set_transition('raman', ctx.p.frequency_raman_transition
                                        + ctx.p.frequency_ramsey_detuning)

        Each drive's IF comes from the channel's transition_to_ifs -- for
        the Raman pair, the same split ARTIQ's RamanBeamPair runs. Every
        shot starts at the run's transition (transition_param): the builder
        restores it after any shot whose body changed a drive frequency.
        For an offset computed ON the OPX see set_transition_offset."""
        self._check_open("set_transition")
        self._claimed_spec(role)
        self._if_touched.add(role)
        self._point_transition(role, f, macro='set_transition',
                               keep_phase=keep_phase)

    def _transition_spec(self, role):
        spec = self._map.spec(role)
        if spec.transition_to_ifs is None:
            raise RuntimeError(
                f"[opx] channel {role!r} has no transition_to_ifs in the "
                f"channel map -- its drives do not address one transition. "
                f"Use ctx.set_frequency per drive instead.")
        return spec

    def _point_transition(self, role, f, macro, phase=PHASE_BODY,
                          keep_phase=False):
        """update_frequency on every drive of `role` to address transition
        f -- shared by set_transition and the builder's per-shot framing
        (which runs outside the body, so no open/claim bookkeeping here)."""
        from qm import qua
        spec = self._transition_spec(role)
        if isinstance(f, ParamRef):
            self._check_ref(f)
            label, col = f.label, f.column
        else:
            label = 'transition'
            col = np.full(self._tables.n_shots,
                          as_host_scalar(f, 'ctx.set_transition() argument'))
        self._check_finite(f, label, col)
        ifs = spec.transition_to_ifs(col)
        missing = set(spec.analog_elements) - set(ifs)
        if missing:
            raise RuntimeError(
                f"[opx] transition_to_ifs for {role!r} gives no IF for "
                f"{sorted(missing)}.")
        self._log.new_call(macro)
        for el in spec.analog_elements:
            ref = ParamRef(f"{el} IF @ {label}", ifs[el], self._tables)
            v = self.hz(ref)
            _label, raw, hz_col = self._last_resolved
            self._log.record('update_frequency', el, phase=phase, macro=macro,
                             label=ref.label, values=raw, duration_cc=None,
                             note=f'IF for transition {label}',
                             frequency_hz=hz_col)
            qua.update_frequency(el, v, keep_phase=keep_phase)

    @staticmethod
    def _if_slope(to_ifs, f_run, el):
        """d IF_el / d f_transition at f_run, numerically (+-1 kHz), checked
        linear to _SLOPE_REL_TOL over _SLOPE_CHECK_HZ. Returns (IF0 int Hz,
        slope)."""
        def at(f):
            return float(np.asarray(to_ifs(np.array([f]))[el]).reshape(-1)[0])
        h = 1.e3
        if0 = at(f_run)
        slope = (at(f_run + h) - at(f_run - h)) / (2. * h)
        for df in _SLOPE_CHECK_HZ:
            actual = at(f_run + df)
            pred = if0 + slope * df
            if abs(pred - actual) > _SLOPE_REL_TOL * max(abs(actual), 1.):
                raise RuntimeError(
                    f"[opx] set_transition_offset: the IF of {el!r} is not "
                    f"linear in the transition frequency around "
                    f"{f_run:g} Hz (at {df:+g} Hz: split gives {actual:.6f}, "
                    f"the slope {slope:g} predicts {pred:.6f}) -- a "
                    f"fixed-point slope cannot represent it.")
        if not abs(slope) < QUA_FIXED_LIMIT:
            raise RuntimeError(
                f"[opx] set_transition_offset: slope {slope:g} of {el!r} "
                f"does not fit QUA fixed [-8, 8).")
        return hz_to_int(if0), float(slope)

    def transition_offset_terms(self, role):
        """{analog element: (IF0 int Hz, slope)} for the RUN's transition:
        the drive IF at an offset df from it is IF0 + slope * df, which is
        what set_transition_offset emits. Exposed so a sequence can form
        the integer IFs itself (e.g. to stream the exact applied values)
        and apply them with ctx.set_frequency(role, if_hz, which=element).
        The transition_param column must be constant for the run."""
        self._claimed_spec(role)
        spec = self._transition_spec(role)
        if spec.transition_param is None:
            raise RuntimeError(
                f"[opx] channel {role!r} has no transition_param in the "
                f"channel map.")
        base = getattr(self.p, spec.transition_param)
        if not base.is_constant:
            c = base.column
            raise RuntimeError(
                f"[opx] transition_offset_terms({role!r}): "
                f"{spec.transition_param} varies per shot ({np.min(c):g} .. "
                f"{np.max(c):g}); one run transition is required.")
        f_run = float(base.column[0])
        return {el: self._if_slope(spec.transition_to_ifs, f_run, el)
                for el in spec.analog_elements}

    def set_transition_offset(self, role, df_hz, keep_phase=False):
        """Detune a channel's analog drives by df_hz from the RUN's
        transition (the transition_param column, which must be constant for
        the run -- refused otherwise).

        df_hz: a QUA int expression (an offset the OPX computed, e.g. from
        a posterior), a ctx.p parameter/expression, or a number. Each drive
        gets update_frequency(el, IF0_el + Cast.mul_int_by_fixed(df, slope_el))
        for a QUA expression, where IF0_el is the drive's IF at the run's
        transition and slope_el = d IF_el / d f_transition, found
        numerically from transition_to_ifs (asserted linear to 1e-9 over
        +-2 MHz). A host value goes through the exact split instead
        (transition_to_ifs(f_run + df), per shot). Marks the role so the
        builder restores the run's IFs after the body.
        """
        from qm import qua
        from qm.qua import Cast
        self._check_open("set_transition_offset")
        self._claimed_spec(role)
        spec = self._transition_spec(role)
        if spec.transition_param is None:
            raise RuntimeError(
                f"[opx] channel {role!r} has no transition_param in the "
                f"channel map; set_transition_offset needs the run's "
                f"transition to offset from.")
        base = getattr(self.p, spec.transition_param)
        if not base.is_constant:
            c = base.column
            raise RuntimeError(
                f"[opx] set_transition_offset({role!r}): "
                f"{spec.transition_param} varies per shot ({np.min(c):g} .. "
                f"{np.max(c):g}) -- the offset is taken from ONE run "
                f"transition. Scan the offset instead, or use "
                f"ctx.set_transition with the full per-shot frequency.")
        f_run = float(base.column[0])
        self._if_touched.add(role)

        if is_qua_expr(df_hz):
            self._log.new_call('set_transition_offset')
            for el in spec.analog_elements:
                if0, slope = self._if_slope(spec.transition_to_ifs, f_run, el)
                self._log.record(
                    'update_frequency', el, macro='set_transition_offset',
                    label=f'{el} IF0 + slope * df(QUA)', duration_cc=None,
                    note=(f'IF = {if0} Hz + {slope:g} * df, df computed on '
                          f'the OPX'),
                    if0_hz=if0, slope=slope, frequency_hz=None)
                qua.update_frequency(
                    el, if0 + Cast.mul_int_by_fixed(df_hz, slope),
                    keep_phase=keep_phase)
            return

        # host value: the exact split at f_run + df, per shot
        if isinstance(df_hz, ParamRef):
            self._check_ref(df_hz)
            label, col = df_hz.label, df_hz.column
        else:
            label = 'df'
            col = np.full(self._tables.n_shots,
                          as_host_scalar(df_hz,
                                         'ctx.set_transition_offset() df_hz'))
        self._check_finite(df_hz, label, col)
        ifs = spec.transition_to_ifs(f_run + col)
        self._log.new_call('set_transition_offset')
        for el in spec.analog_elements:
            if0, slope = self._if_slope(spec.transition_to_ifs, f_run, el)
            ref = ParamRef(f"{el} IF @ ({spec.transition_param} + {label})",
                           ifs[el], self._tables)
            v = self.hz(ref)
            _l, raw, hz_col = self._last_resolved
            self._log.record('update_frequency', el,
                             macro='set_transition_offset', label=ref.label,
                             values=raw, duration_cc=None,
                             note=f'IF for the run transition + {label}',
                             frequency_hz=hz_col, if0_hz=if0, slope=slope)
            qua.update_frequency(el, v, keep_phase=keep_phase)

    def frame_rotation(self, role, turns, which=None):
        """Rotate the frame of a channel's analog drive(s) by `turns`
        (fraction of 2pi; SI-free; a ctx.p parameter scans per shot)."""
        from qm import qua
        self._check_open("frame_rotation")
        els = self._analog_targets(role, which)
        self._log.new_call('frame_rotation')
        v = self.f(turns)
        label, raw, col = self._last_resolved
        for el in els:
            self._log.record('frame_rotation_2pi', el, macro='frame_rotation',
                             label=label, values=raw, note='frame rotation',
                             turns=col)
            qua.frame_rotation_2pi(v, el)

    def reset_frame(self, role, which=None):
        """Zero the frame of a channel's analog drive(s)."""
        from qm import qua
        self._check_open("reset_frame")
        self._log.new_call('reset_frame')
        for el in self._analog_targets(role, which):
            self._log.record('reset_frame', el, macro='reset_frame',
                             note='frame reset to 0')
            qua.reset_frame(el)

    # ------------------------------------------------------------------
    # Streams, saves, loops, per-shot tables
    # ------------------------------------------------------------------

    def stream(self, key):
        """The declared output stream for data key `key` (declared on first
        use). The key must be in the sequence's measurements."""
        from qm import qua
        if key not in self._measurements:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r} streams into "
                f"{key!r}, which is not declared in its measurements={{...}}.")
        if key not in self._streams:
            self._streams[key] = qua.declare_output_stream()
            self._save_counts.setdefault(key, 0)
        return self._streams[key]

    def _get_stream(self, key):
        """(stream, measure variable) for a measure() key."""
        from qm import qua
        stream = self.stream(key)
        if key not in self._measure_vars:
            self._measure_vars[key] = qua.declare(qua.fixed)
        return stream, self._measure_vars[key]

    def save(self, key, expr):
        """qua.save(expr, stream of key): one save on `key` per call
        (multiplied by the enclosing ctx.for_range counts). expr: any QUA
        scalar (variable, array cell, expression) or a Python number."""
        from qm import qua
        stream = self.stream(key)
        self._log.new_call('save')
        self._log.record('save', None, macro='save', data_key=key,
                         note=f'save into {key!r}')
        qua.save(expr, stream)
        self._count_save(key)

    def _loop_count(self, n):
        if isinstance(n, ParamRef):
            n = self.const(n)
        if is_qua_expr(n):
            raise TypeError(
                "[opx] ctx.for_range(n): n must be a Python int (the saves "
                "inside are counted at trace time), not a QUA expression. "
                "Use ctx.qua.for_ directly for a run-time bound, and "
                "declare its saves with a fixed shape.")
        v = as_host_scalar(n, 'ctx.for_range() count')
        if v != int(v) or v < 1:
            raise ValueError(
                f"[opx] ctx.for_range(n): n must be a positive integer, "
                f"got {n!r}.")
        return int(v)

    @contextlib.contextmanager
    def for_range(self, n):
        """``with ctx.for_range(n) as i:`` -- a QUA loop
        for_(i, 0, i < n, i + 1). n must be a Python int (or a ctx.p
        parameter constant for the run; ctx.const rules apply). Saves
        inside count n times for the per-shot validation."""
        from qm import qua
        n = self._loop_count(n)
        i = qua.declare(int)
        self._log.new_call('for_range')
        self._log.record('for', None, macro='for_range', count=n,
                         note=f'QUA loop of {n} iterations')
        self._loop_stack.append(n)
        self._log.loop_scale = self._loop_scale()
        try:
            with qua.for_(i, 0, i < n, i + 1):
                yield i
        finally:
            self._loop_stack.pop()
            self._log.loop_scale = self._loop_scale()

    def shot_array(self, key, values, dtype=float) -> ShotArray:
        """Ship a host-drawn per-shot table to the OPX as ONE flat QUA
        array: values of shape (n_shots,) or (n_shots, M), execution
        order, declared as qua.declare(int|fixed, value=flat).
        ShotArray.at(i) -> qua_array[ctx.shot * M + i].

        Validated finite; int32 range (and integral) for dtype=int, QUA
        fixed [-8, 8) for dtype=float. Recorded in ctx._shot_arrays for
        provenance (the manager saves the shapes; hand the same values to
        ctx.host_data to save them in the run file).

        Size the table from ctx.n_shots, never from a number the sequence
        assumes: a simulation re-traces the body on the tables sliced to
        simulate_shots, and the row count must follow.
        """
        from qm import qua
        key = str(key)
        if key in self._shot_arrays:
            raise RuntimeError(
                f"[opx] shot_array({key!r}) declared twice in sequence "
                f"{self._sequence.name!r}.")
        dtype = _as_dtype(dtype)
        vals = np.asarray(values, dtype=float)
        if vals.ndim == 1:
            table = vals[:, None]
        elif vals.ndim == 2:
            table = vals
        else:
            raise ValueError(
                f"[opx] shot_array({key!r}): values must be (n_shots,) or "
                f"(n_shots, M), got shape {vals.shape}.")
        if table.shape[0] != self._tables.n_shots:
            raise ValueError(
                f"[opx] shot_array({key!r}): values have {table.shape[0]} "
                f"rows but the run has {self._tables.n_shots} shots "
                f"(execution order, one row per shot).")
        if table.shape[1] < 1:
            raise ValueError(f"[opx] shot_array({key!r}): M must be >= 1.")
        self._check_finite(None, key, table.ravel())
        flat = table.ravel()
        if dtype is int:
            if np.any(flat != np.rint(flat)):
                raise ValueError(
                    f"[opx] shot_array({key!r}, dtype=int): values are not "
                    f"integral (first: {flat[np.flatnonzero(flat != np.rint(flat))[0]]!r}).")
            self._check_int32(key, flat)
            arr = qua.declare(int, value=[int(v) for v in flat])
        else:
            self._check_fixed(key, flat)
            arr = qua.declare(qua.fixed, value=[float(v) for v in flat])
        self._shot_arrays[key] = vals.copy()
        self._shot_arrays_qua[key] = arr
        return ShotArray(self, key, vals, dtype, arr)

    def host_data(self, key, values):
        """Record host-computed per-shot values (n_shots, *shape) for the
        container declared in the sequence's host_data={key: shape}; written
        at finish, never volts-converted. Execution order, one row per
        shot."""
        spec = self._host_data_specs.get(key)
        if spec is None:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: host_data({key!r}) "
                f"is not declared in its host_data={{...}}.")
        if key in self._host_data_values:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: host_data({key!r}) "
                f"written twice.")
        vals = np.asarray(values, dtype=float)
        expect = (self._tables.n_shots, *spec.shape)
        if vals.shape != expect:
            if (vals.ndim >= 1 and vals.shape[0] == expect[0]
                    and vals.size == int(np.prod(expect))):
                vals = vals.reshape(expect)
            else:
                raise ValueError(
                    f"[opx] host_data({key!r}): expected shape "
                    f"{_fmt_shape(expect)} (n_shots, *{spec.shape}), got "
                    f"{_fmt_shape(vals.shape)}.")
        self._host_data_values[key] = vals.copy()

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def measure(self, key, role='imaging', expose=True, t_expose=None,
                timestamp_key=None, expose_timestamp_key=None):
        """One integrated detector acquisition, saved into data key ``key``.
        Returns the QUA fixed variable holding the raw integration result
        (one per key; usable by the statements that follow).

        expose=True opens the channel's RF block for the acquire window
        (t_expose seconds, default the config acquire length; a QUA int
        expression is clock cycles) so the beam reaches the atoms/detector;
        expose=False keeps it blocked (dark / background shot). The ADC
        window always runs. timestamp_key records the measure's start
        time into a declared int stream (one save on that key);
        expose_timestamp_key does the same for the exposure's 'pass' play
        on the switch element (requires expose=True).
        """
        from qm import qua
        self._check_open(f"measure({key!r})")
        spec = self._claimed_spec(role)
        if spec.measure_element is None:
            raise RuntimeError(
                f"[opx] channel {role!r} has no measure element.")
        mspec = self._measurements.get(key)
        if mspec is not None and mspec.dtype is int:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: measure({key!r}) "
                f"saves a QUA fixed, but {key!r} is declared as an int "
                f"stream.")
        stream, ivar = self._get_stream(key)
        self._stream_roles[key] = role
        ts_stream = (self._timestamp_stream(timestamp_key, f'measure({key!r})')
                     if timestamp_key is not None else None)
        if expose_timestamp_key is not None and not expose:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r}: measure({key!r}, "
                f"expose=False) plays no exposure to timestamp "
                f"(expose_timestamp_key={expose_timestamp_key!r}).")
        ts_expose = (self._timestamp_stream(expose_timestamp_key,
                                            f'measure({key!r}) exposure')
                     if expose_timestamp_key is not None else None)
        n_prev = self._save_counts[key]
        which = f"{key}[{n_prev}]"

        self._log.new_call('measure')
        self._log.record('align', None, macro='measure', data_key=key,
                         note=f'align {spec.switch_element} and '
                              f'{spec.measure_element}',
                         elements=[spec.switch_element,
                                   spec.measure_element])
        qua.align(spec.switch_element, spec.measure_element)
        if expose:
            t = t_expose if t_expose is not None else spec.t_acquire_s
            d = self.cc(t, key=f"{key} exposure")
            label, raw, cc_col = self._last_resolved
            self._log.record('play', spec.switch_element, spec.pass_op,
                             macro='measure', label=label, values=raw,
                             duration_cc=cc_col, data_key=key,
                             note=f'{role} exposure for {which}'
                                  + (f'; start timestamped into '
                                     f'{expose_timestamp_key!r}'
                                     if ts_expose is not None else ''))
            qua.play(spec.pass_op, spec.switch_element, duration=d,
                     timestamp_stream=ts_expose)
            if ts_expose is not None:
                self._count_save(expose_timestamp_key)
            self._log.record('play', spec.switch_element, spec.block_op,
                             macro='measure', data_key=key,
                             note=f'{role} re-blocked')
            qua.play(spec.block_op, spec.switch_element)
        self._log.record('measure', spec.measure_element, spec.acquire_op,
                         macro='measure', data_key=key,
                         note=(f'ADC window for {which}'
                               + ('' if expose else ' (dark: beam blocked)')
                               + (f'; start timestamped into {timestamp_key!r}'
                                  if timestamp_key else '')),
                         dark=not expose)
        qua.measure(spec.acquire_op, spec.measure_element,
                    qua.integration.full(spec.integration_weight, ivar,
                                         'out1'),
                    timestamp_stream=ts_stream)
        if timestamp_key is not None:
            self._count_save(timestamp_key)
        self._log.record('save', None, macro='measure', data_key=key,
                         note=f'save {which}')
        qua.save(ivar, stream)
        self._count_save(key)
        return ivar

    # ------------------------------------------------------------------
    # Handshake / timing
    # ------------------------------------------------------------------

    def handback_to_artiq(self):
        """Hand control back to ARTIQ.

        Fires the hand-back trigger, then -- counted from its rising edge --
        holds every guarded RF block high and every guarded analog drive
        untouched for ChannelMap.t_handback_hold_s: the sum of
        t_opx_handback_artiq_trigger_receive_latency (the edge reaches
        ARTIQ's timestamp), t_opx_handback_artiq_rtio_delay (ARTIQ's
        wait_for_quantum_machines_handback switches its steady-state RF off
        and drops the handoff TTL that long after its timestamp) and
        t_opx_handback_switch_fall_delay (those switches have fallen). Then
        it releases the blocks to pass so ARTIQ owns its own light between
        shots. The drives wait with the blocks, so whatever the program
        does to them next -- the epilogue's ramp_to_zero after the final
        shot, an IF re-point -- happens only once ARTIQ has the AOs back.
        Auto-appended at the end of the body if the sequence never calls
        it. It may be called explicitly, but it must be the body's last act
        on the beams: nothing may play or measure after it (see
        _check_open).
        """
        from qm import qua
        if self._handback_done:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r} calls "
                f"handback_to_artiq() more than once per shot.")
        log, phase = self._log, self._handback_phase()
        log.new_call('handback')
        log.record('align', None, phase=phase, macro='handback',
                   note='align before the hand-back')
        qua.align()
        log.record('play', self._map.handback_element, self._map.handback_op,
                   phase=phase, macro='handback',
                   note='hand-back trigger to ARTIQ')
        qua.play(self._map.handback_op, self._map.handback_element)
        # the wait starts with the trigger play (all aligned above), so the
        # hold is counted from the rising edge
        switches = [s.switch_element for s in self._guarded_specs]
        held = switches + [el for s in self._guarded_specs
                           for el in s.analog_elements]
        log.record('wait', held[0] if held else None, phase=phase,
                   macro='handback', label='t_handback_hold_s',
                   duration_cc=self._hold_cc,
                   values=self._hold_cc * 4e-9,
                   note='blocks held and drives untouched while ARTIQ '
                        'takes its RF and the AOs back (receive latency '
                        '+ rtio delay + switch fall)',
                   elements=list(held))
        qua.wait(self._hold_cc, *held)
        for s in self._guarded_specs:
            log.record('play', s.switch_element, s.pass_op, phase=phase,
                       macro='handback',
                       note='block released: ARTIQ owns this beam again')
            qua.play(s.pass_op, s.switch_element)
        self._handback_done = True

    def _handback_phase(self):
        """Explicit handback_to_artiq() from the body carries the body's
        source line; the builder's auto-append is handshake framing."""
        from kexp.control.opx.trace_log import PHASE_HANDSHAKE
        src = self._log.capture_source(skip=3)
        return PHASE_BODY if src is not None else PHASE_HANDSHAKE

    def wait_s(self, t):
        """Advance all elements together by t seconds (SI; a ctx.p
        parameter scans per shot; a QUA int expression is clock cycles):
        one align, then a wait on every element of the map. A per-shot
        value that is 0 on some shots is guarded (nothing waits there)."""
        from qm import qua
        self._check_open("wait_s")
        d = self.cc(t, key='wait')
        label, raw, cc_col = self._last_resolved
        els = self._all_elements()
        log = self._log
        log.new_call('wait_s')
        log.record('align', None, macro='wait_s')
        qua.align()
        if isinstance(d, (int, np.integer)):
            if d == 0:
                log.record('wait', els[0], macro='wait_s', label=label,
                           values=raw, duration_cc=cc_col, elements=els,
                           executes=np.zeros(self._tables.n_shots, bool),
                           note='zero wait: nothing emitted')
                return
            log.record('wait', els[0], macro='wait_s', label=label,
                       values=raw, duration_cc=cc_col, elements=els,
                       note='all elements wait together')
            qua.wait(d, *els)
            return
        runs = (cc_col >= MIN_PULSE_CC) if cc_col is not None else None
        log.record('if', None, macro='wait_s', label=label, values=raw,
                   duration_cc=cc_col, executes=runs,
                   note=f'skipped on shots where {label} < 16 ns')
        with qua.if_(d >= MIN_PULSE_CC):
            log.record('wait', els[0], macro='wait_s', label=label,
                       values=raw, duration_cc=cc_col, elements=els,
                       executes=runs, note='all elements wait together')
            qua.wait(d, *els)

    def wait_cc(self, d, *names):
        """Raw wait of d clock cycles (a Python int or a QUA int expression;
        no host checks on a QUA value) on the named elements only. Names
        are channel roles (-> the role's switch element) or element names
        of the map. At least one name is required: a raw wait is explicit
        about what it stalls."""
        from qm import qua
        self._check_open("wait_cc")
        if not names:
            raise TypeError("[opx] ctx.wait_cc(d, *names): name at least one "
                            "element or role to wait on.")
        els = [self._element_name(n) for n in names]
        log = self._log
        log.new_call('wait_cc')
        if is_qua_expr(d):
            log.record('wait', els[0], macro='wait_cc', elements=els,
                       label='<QUA expression>', note='raw wait, QUA duration')
            qua.wait(d, *els)
            return
        v = as_host_scalar(d, 'ctx.wait_cc() duration')
        if v != int(v) or v < 0:
            raise ValueError(f"[opx] ctx.wait_cc: duration must be a "
                             f"non-negative integer of clock cycles, got {d!r}")
        v = int(v)
        if 0 < v < MIN_PULSE_CC:
            raise ValueError(f"[opx] ctx.wait_cc: {v} cycles is under the OPX "
                             f"minimum of {MIN_PULSE_CC} (16 ns).")
        self._check_int32('ctx.wait_cc() duration', np.array([v]))
        if v == 0:
            log.record('wait', els[0], macro='wait_cc', elements=els,
                       duration_cc=0,
                       executes=np.zeros(self._tables.n_shots, bool),
                       note='zero wait: nothing emitted')
            return
        log.record('wait', els[0], macro='wait_cc', elements=els,
                   duration_cc=v, values=v * 4e-9, note='raw wait')
        qua.wait(v, *els)

    def align(self, *names):
        """qua.align on the named elements (channel roles -> their switch
        element; element names of the map as-is); no names = global."""
        from qm import qua
        els = [self._element_name(n) for n in names]
        self._log.new_call('align')
        self._log.record('align', None, macro='align',
                         elements=(els if els else None),
                         note=('align ' + ', '.join(els)) if els
                         else 'global align')
        qua.align(*els)
