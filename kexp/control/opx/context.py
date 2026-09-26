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

Generic (future waxx.control.opx): no kexp imports; qm imported inside
methods only.
"""

from typing import Generic, TypeVar, cast

import numpy as np

from kexp.control.opx.params_bridge import (ParamRef, ParamsProxy, ShotTables,
                                            as_host_scalar)
from kexp.control.opx.channels import ChannelMap
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


class OPXShotContext(Generic[P]):

    p: P

    def __init__(self, channel_map: ChannelMap, tables: ShotTables,
                 sequence, shot_var, overlap_cc, guarded_specs, log=None):
        self.p = cast(P, ParamsProxy(tables))
        self._map = channel_map
        self._tables = tables
        self._sequence = sequence
        self._shot = shot_var
        self._overlap_cc = int(overlap_cc)
        self._guarded_specs = list(guarded_specs)

        self._qua_arrays = {}    # (key, tag) -> declared QUA array
        self._streams = {}       # data key -> (stream, qua fixed variable)
        self._stream_roles = {}  # data key -> channel role (for V conversion)
        self._save_counts = {}   # data key -> saves traced per shot
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
        whether it happens to be scanned this run.
        """
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
        varies per shot. Use for play/wait durations."""
        name = t.label if isinstance(t, ParamRef) else key
        what = f"{key} duration" if key else "ctx.cc() argument"
        return self._resolve(t, lambda c: s_to_cc(c, key=name), 'cc', int,
                             what)

    def hz(self, f):
        """Hz -> integer Hz (for update_frequency)."""
        return self._resolve(f, hz_to_int, 'hz', int, 'ctx.hz() argument')

    def f(self, x):
        """Plain float (e.g. an amp() scaling factor): float if fixed, QUA
        fixed expression if it varies per shot. Must fit QUA fixed, [-8, 8)."""
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
        the OPX is not exposed in v1.
        """
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

    # ------------------------------------------------------------------
    # Exposure / pulses
    # ------------------------------------------------------------------

    def _expose(self, role, t):
        """Open a channel's RF block for t seconds, then re-block.

        The switch elements are sticky-digital: 'pass' holds the line low
        (RF through) until 'block' re-raises it, so the exposure is exactly
        the played 'pass' duration with no gap before the re-block.
        """
        from qm import qua
        self._check_open(f"pulse on {role!r}")
        spec = self._claimed_spec(role)
        self._log.new_call(f"{role}_pulse")
        d = self.cc(t, key=f"{role} pulse")
        label, raw, cc_col = self._last_resolved
        macro = f"{role}_pulse"
        el = spec.switch_element
        if isinstance(d, (int, np.integer)):
            if d == 0:
                self._log.record('play', el, spec.pass_op, macro=macro,
                                 label=label, values=raw, duration_cc=cc_col,
                                 executes=np.zeros(self._tables.n_shots, bool),
                                 note='zero-length pulse: nothing played')
                return          # a zero-length pulse is no pulse
            self._log.record('play', el, spec.pass_op, macro=macro,
                             label=label, values=raw, duration_cc=cc_col,
                             note=f'{role} exposure (RF passes)')
            qua.play(spec.pass_op, el, duration=d)
            self._log.record('play', el, spec.block_op, macro=macro,
                             label=label, values=raw,
                             note=f'{role} re-blocked')
            qua.play(spec.block_op, el)
        else:
            # duration varies per shot and may be zero on some shots (e.g.
            # a Rabi scan from t = 0): branch on the OPX
            runs = cc_col >= MIN_PULSE_CC
            self._log.record('if', None, macro=macro, label=label,
                             values=raw, duration_cc=cc_col, executes=runs,
                             note=f'skipped on shots where {label} < 16 ns')
            with qua.if_(d >= MIN_PULSE_CC):
                self._log.record('play', el, spec.pass_op, macro=macro,
                                 label=label, values=raw, duration_cc=cc_col,
                                 executes=runs,
                                 note=f'{role} exposure (RF passes)')
                qua.play(spec.pass_op, el, duration=d)
                self._log.record('play', el, spec.block_op, macro=macro,
                                 label=label, values=raw, executes=runs,
                                 note=f'{role} re-blocked')
                qua.play(spec.block_op, el)

    def raman_pulse(self, t):
        """Expose the atoms to the Raman beams for t seconds (SI)."""
        self._expose('raman', t)

    def imaging_pulse(self, t):
        """Expose the atoms to the imaging beam for t seconds (SI)."""
        self._expose('imaging', t)

    def raman_phase_reset(self):
        """Zero the relative phase of the Raman analog drives.

        Not part of raman_pulse by default: reset_if_phase briefly occupies
        the analog cores, and a single-pulse experiment (Rabi) does not care
        about the two-photon phase origin. Multi-pulse sequences call this
        before their first pulse.
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
        to f Hz (SI; a ctx.p parameter scans per shot). `which` selects
        one drive by index or element name (default: every drive of the
        role). The change takes effect on the sticky drive immediately."""
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
        restores it after any shot whose body changed a drive frequency."""
        self._check_open("set_transition")
        self._claimed_spec(role)
        self._if_touched.add(role)
        self._point_transition(role, f, macro='set_transition',
                               keep_phase=keep_phase)

    def _point_transition(self, role, f, macro, phase=PHASE_BODY,
                          keep_phase=False):
        """update_frequency on every drive of `role` to address transition
        f -- shared by set_transition and the builder's per-shot framing
        (which runs outside the body, so no open/claim bookkeeping here)."""
        from qm import qua
        spec = self._map.spec(role)
        if spec.transition_to_ifs is None:
            raise RuntimeError(
                f"[opx] channel {role!r} has no transition_to_ifs in the "
                f"channel map -- its drives do not address one transition. "
                f"Use ctx.set_frequency per drive instead.")
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
    # Measurement
    # ------------------------------------------------------------------

    def _get_stream(self, key):
        from qm import qua
        if key not in self._sequence.measurements:
            raise RuntimeError(
                f"[opx] sequence {self._sequence.name!r} measures into "
                f"{key!r}, which is not declared in its measurements={{...}}.")
        if key not in self._streams:
            self._streams[key] = (qua.declare_output_stream(),
                                  qua.declare(qua.fixed))
            self._save_counts[key] = 0
        return self._streams[key]

    def measure(self, key, role='imaging', expose=True, t_expose=None):
        """One integrated detector acquisition, saved into data key ``key``.

        expose=True opens the channel's RF block for the acquire window
        (t_expose seconds, default the config acquire length) so the beam
        reaches the atoms/detector; expose=False keeps it blocked (dark /
        background shot). The ADC window always runs.
        """
        from qm import qua
        self._check_open(f"measure({key!r})")
        spec = self._claimed_spec(role)
        if spec.measure_element is None:
            raise RuntimeError(
                f"[opx] channel {role!r} has no measure element.")
        stream, ivar = self._get_stream(key)
        self._stream_roles[key] = role
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
                             note=f'{role} exposure for {which}')
            qua.play(spec.pass_op, spec.switch_element, duration=d)
            self._log.record('play', spec.switch_element, spec.block_op,
                             macro='measure', data_key=key,
                             note=f'{role} re-blocked')
            qua.play(spec.block_op, spec.switch_element)
        self._log.record('measure', spec.measure_element, spec.acquire_op,
                         macro='measure', data_key=key,
                         note=(f'ADC window for {which}'
                               + ('' if expose else ' (dark: beam blocked)')),
                         dark=not expose)
        qua.measure(spec.acquire_op, spec.measure_element,
                    qua.integration.full(spec.integration_weight, ivar,
                                         'out1'))
        self._log.record('save', None, macro='measure', data_key=key,
                         note=f'save {which}')
        qua.save(ivar, stream)
        self._save_counts[key] += 1

    # ------------------------------------------------------------------
    # Handshake / timing
    # ------------------------------------------------------------------

    def handback_to_artiq(self):
        """Hand control back to ARTIQ.

        Fires the hand-back trigger, holds every guarded RF block high for
        the shared overlap window (ExptParams.t_opx_handback_overlap --
        ARTIQ's wait_for_quantum_machines_handback kills its steady-state
        RF halfway through it), then releases the blocks to pass so ARTIQ
        owns its own light between shots. Auto-appended at the end of the
        body if the sequence never calls it. It may be called explicitly, but
        it must be the body's last act on the beams: nothing may play or
        measure after it (see _check_open).
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
        switches = [s.switch_element for s in self._guarded_specs]
        log.record('wait', switches[0] if switches else None, phase=phase,
                   macro='handback', label='t_opx_handback_overlap',
                   duration_cc=self._overlap_cc,
                   values=self._overlap_cc * 4e-9,
                   note='blocks held while ARTIQ takes its RF back',
                   elements=list(switches))
        qua.wait(self._overlap_cc, *switches)
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
        """Advance all elements together by t seconds (SI)."""
        from qm import qua
        self._check_open("wait_s")
        d = self.cc(t, key='wait')
        label, raw, cc_col = self._last_resolved
        sync_el = self._map.spec(self._map.sync_channel).switch_element
        self._log.new_call('wait_s')
        self._log.record('align', None, macro='wait_s')
        qua.align()
        self._log.record('wait', sync_el, macro='wait_s', label=label,
                         values=raw, duration_cc=cc_col,
                         note='all elements wait together')
        qua.wait(d, sync_el)
        self._log.record('align', None, macro='wait_s')
        qua.align()

    def align(self):
        from qm import qua
        self._log.new_call('align')
        self._log.record('align', None, macro='align')
        qua.align()
