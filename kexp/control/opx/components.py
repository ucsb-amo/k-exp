"""QUAM-shaped component layer for the OPX config.

Each OPX element is a small dataclass that writes its own slice of the QUA
config (``apply_to_config``); a ``Machine`` holds the elements, runs them
over a config template (``generate_config``) and serialises itself to a
JSON-able dict with ``__class__`` entries (``to_dict``) for run-file
provenance. The shapes are borrowed from QUAM
(https://qua-platform.github.io/quam/: ``QuamComponent.apply_to_config``,
``QuamRoot.generate_config``, ``StickyChannelAddon``, ``to_dict`` with
``__class__``) without taking quam as a dependency -- the phase-1 report
quam_docs.md, sections 7c/7d (Variant B), has the reasons: quam resolves
its references on the host at trace time and cannot express "this value is
a per-shot column of the ARTIQ scan", which is the one thing our
params_bridge does; its measure() is demod-only; it imports qm at module
level.

Naming rule (QUAM's): every config entry a pulse needs is derived from the
element name and the operation label --

    <element>.<label>.pulse            pulses
    <element>.<label>.wf               waveforms (analog)
    <element>.<label>.dm               digital_waveforms (marker)
    <element>.<label>.<weight>.iw      integration_weights

-- so two elements can never collide on a pulse name and a config entry
reads back to the element that owns it. Element names and operation labels
themselves are whatever the lab gives them (kexp opx_config.build_machine);
they are the only names the QUA program text refers to, so a sequence, the
op log and the pulse viewer never see the derived names. Element names and
labels must not contain '.', so the rule stays reversible.

Not copied from QUAM on purpose: string references, typeguard validation,
the QUAlibrate config file, the seeded ``const_pulse``/``ON`` template
entries, and load() -- to_dict() is provenance, not a round trip.

Generic (future waxx.control.opx): no kexp imports, no qm imports.
"""

import copy
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import numpy as np

from kexp.control.opx.units import MAX_ANALOG_V, CLOCK_NS, MIN_PULSE_CC


def _controller(cfg, con, controller_type='opx1'):
    return cfg['controllers'].setdefault(con, {'type': controller_type})


def _check_name(what, s):
    if not isinstance(s, str) or not s:
        raise ValueError(f"[opx] {what} must be a non-empty string, got {s!r}.")
    if '.' in s:
        raise ValueError(
            f"[opx] {what} {s!r} contains '.', which the "
            f"<element>.<label>.pulse naming rule reserves.")


def _check_length_ns(what, ns):
    ns = int(ns)
    if ns < MIN_PULSE_CC * CLOCK_NS or ns % CLOCK_NS:
        raise ValueError(
            f"[opx] {what} = {ns} ns must be a multiple of {CLOCK_NS} ns and "
            f"at least {MIN_PULSE_CC * CLOCK_NS} ns (the OPX minimum pulse).")
    return ns


def _plain(x):
    """Recursively turn numpy scalars/arrays and tuples into JSON-able
    python values (tuples -> lists, as json.dumps would)."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return [_plain(v) for v in x.tolist()]
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    return x


def _class_path(obj):
    t = type(obj)
    return f"{t.__module__}.{t.__qualname__}"


# ---------------------------------------------------------------------------
# addons
# ---------------------------------------------------------------------------

@dataclass(kw_only=True)
class Sticky:
    """Sticky-element settings (QUAM's StickyChannelAddon).

    duration_ns: the ramp-to-zero time, in ns (what the config's
    'sticky.duration' means). The QOP requires analog=True even on a
    digital-only sticky element ("sticky digital but analog sticky wasn't
    set" job failure otherwise); it is a no-op without analog waveforms.
    to_config writes 'digital' only when it is True (the QOP default is
    False), so an analog drive's sticky dict stays {'analog', 'duration'}
    exactly as the hand-written config had it.
    """
    duration_ns: int
    analog: bool = True
    digital: bool = True

    def to_config(self) -> dict:
        d = {'analog': bool(self.analog)}
        if self.digital:
            d['digital'] = True
        d['duration'] = int(self.duration_ns)
        return d


# ---------------------------------------------------------------------------
# elements
# ---------------------------------------------------------------------------

@dataclass(kw_only=True)
class Element:
    """One QUA element: a name, a controller, optional sticky/core, and the
    operations it plays (``labels``). Subclasses own the ports and write
    their config slice in ``apply_to_config(cfg)``."""
    name: str
    con: str = 'con1'
    sticky: Optional[Sticky] = None
    core: Optional[str] = None

    # --- the naming rule ---------------------------------------------------
    def op_name(self, label) -> str:
        return f"{self.name}.{label}"

    def pulse_name(self, label) -> str:
        return f"{self.op_name(label)}.pulse"

    def waveform_name(self, label) -> str:
        return f"{self.op_name(label)}.wf"

    def marker_name(self, label) -> str:
        return f"{self.op_name(label)}.dm"

    def weight_name(self, label, weight) -> str:
        return f"{self.op_name(label)}.{weight}.iw"

    @property
    def labels(self) -> tuple:
        """Operation labels this element plays -- the names QUA play() /
        measure() use, and the keys of the element's 'operations'."""
        raise NotImplementedError

    def operations(self) -> dict:
        return {label: self.pulse_name(label) for label in self.labels}

    # --- ports (for the machine-level clash check) --------------------------
    @property
    def digital_output_ports(self) -> tuple:
        return ()

    @property
    def analog_output_ports(self) -> tuple:
        return ()

    # --- config ------------------------------------------------------------
    def validate(self):
        _check_name('element name', self.name)
        for label in self.labels:
            _check_name(f'operation label of {self.name!r}', label)
        if self.sticky is not None and int(self.sticky.duration_ns) <= 0:
            raise ValueError(
                f"[opx] {self.name!r}: sticky duration must be positive "
                f"(got {self.sticky.duration_ns!r} ns).")

    def _element_base(self) -> dict:
        d = {}
        if self.sticky is not None:
            d['sticky'] = self.sticky.to_config()
        if self.core is not None:
            d['core'] = self.core
        d['operations'] = self.operations()
        return d

    def apply_to_config(self, cfg) -> None:
        raise NotImplementedError


@dataclass(kw_only=True)
class DigitalLine(Element):
    """Digital-only element on one digital output port, with one level-set
    operation per entry of ``levels`` ({label: 0|1}): the pulse is
    ``edge_ns`` long and its marker holds ``level`` for the whole pulse. On a
    sticky line the level then holds until the next play (an RF-block
    switch: levels={'block': 1, 'pass': 0}); on a non-sticky line the pulse
    is a ``edge_ns``-long flag (a trigger: levels={'trigger': 1},
    edge_ns=200)."""
    port: int
    levels: dict = field(default_factory=lambda: {'block': 1, 'pass': 0})
    edge_ns: int = 16

    @property
    def labels(self) -> tuple:
        return tuple(self.levels)

    @property
    def digital_output_ports(self) -> tuple:
        return (int(self.port),)

    def validate(self):
        super().validate()
        if not self.levels:
            raise ValueError(f"[opx] {self.name!r} has no operations.")
        for label, lvl in self.levels.items():
            if int(lvl) not in (0, 1):
                raise ValueError(
                    f"[opx] {self.name!r}.{label}: level must be 0 or 1, "
                    f"got {lvl!r}.")
        _check_length_ns(f'{self.name!r} edge_ns', self.edge_ns)

    def apply_to_config(self, cfg) -> None:
        e = {'digitalInputs': {'in': {'port': (self.con, int(self.port)),
                                      'delay': 0, 'buffer': 0}}}
        e.update(self._element_base())
        for label, lvl in self.levels.items():
            cfg['pulses'][self.pulse_name(label)] = {
                'operation': 'control',
                'length': int(self.edge_ns),
                'digital_marker': self.marker_name(label),
            }
            cfg['digital_waveforms'][self.marker_name(label)] = {
                'samples': [(int(lvl), 0)]}
        _controller(cfg, self.con).setdefault(
            'digital_outputs', {})[int(self.port)] = {}
        cfg['elements'][self.name] = e


@dataclass(kw_only=True)
class AnalogDrive(Element):
    """Single analog output holding a constant tone at ``if_hz`` with
    sample amplitude ``amplitude_v`` (V into 50 ohm). One operation, ``op``
    (default 'cw'): a ``latch_ns`` constant pulse -- on a sticky element the
    tone then holds until ramp_to_zero."""
    port: int
    if_hz: int
    amplitude_v: float
    latch_ns: int = 1000
    op: str = 'cw'

    @property
    def labels(self) -> tuple:
        return (self.op,)

    @property
    def analog_output_ports(self) -> tuple:
        return (int(self.port),)

    def validate(self):
        super().validate()
        if abs(float(self.amplitude_v)) > MAX_ANALOG_V:
            raise ValueError(
                f"[opx] {self.name} drive amplitude {self.amplitude_v} V "
                f"exceeds the OPX analog output limit of {MAX_ANALOG_V} V.")
        _check_length_ns(f'{self.name!r} latch_ns', self.latch_ns)
        if int(self.if_hz) != self.if_hz:
            raise ValueError(
                f"[opx] {self.name!r}: if_hz must be an integer Hz "
                f"(got {self.if_hz!r}); use units.hz_to_int.")

    def apply_to_config(self, cfg) -> None:
        e = {'singleInput': {'port': (self.con, int(self.port))},
             'intermediate_frequency': int(self.if_hz)}
        e.update(self._element_base())
        cfg['pulses'][self.pulse_name(self.op)] = {
            'operation': 'control',
            'length': int(self.latch_ns),
            'waveforms': {'single': self.waveform_name(self.op)},
        }
        cfg['waveforms'][self.waveform_name(self.op)] = {
            'type': 'constant', 'sample': float(self.amplitude_v)}
        _controller(cfg, self.con).setdefault(
            'analog_outputs', {})[int(self.port)] = {'offset': 0.0}
        cfg['elements'][self.name] = e


@dataclass(kw_only=True)
class IntegratedInput(Element):
    """Single analog input read with plain integration (integration.full,
    cosine weights only), plus a digital marker on ``marker_port`` for the
    duration of the acquire pulse (a scope marker; the beam is gated by a
    separate DigitalLine). One measurement operation, ``acquire_op``
    (default 'acquire'), ``acquire_ns`` long, carrying two weight sets:
    ``weight`` (default 'integration_window'): 1.0 over
    [window_start_ns, window_start_ns + window_len_ns), 0 elsewhere; and
    ``full_weight`` (default 'full_pulse'): 1.0 over the whole pulse."""
    in_port: int
    marker_port: int
    acquire_ns: int
    window_start_ns: int
    window_len_ns: int
    time_of_flight_ns: int = 200
    gain_db: int = 0
    acquire_op: str = 'acquire'
    weight: str = 'integration_window'
    full_weight: str = 'full_pulse'

    @property
    def labels(self) -> tuple:
        return (self.acquire_op,)

    @property
    def digital_output_ports(self) -> tuple:
        return (int(self.marker_port),)

    @property
    def tail_ns(self) -> int:
        return int(self.acquire_ns) - int(self.window_start_ns) - int(self.window_len_ns)

    @property
    def t_acquire_s(self) -> float:
        return int(self.acquire_ns) * 1e-9

    @property
    def t_window_s(self) -> float:
        return int(self.window_len_ns) * 1e-9

    def window(self) -> list:
        """[(weight, ns), ...] for the integration window, zero-length
        pieces dropped."""
        w = [(0.0, int(self.window_start_ns)), (1.0, int(self.window_len_ns)),
             (0.0, int(self.tail_ns))]
        return [(v, ns) for v, ns in w if ns > 0]

    def validate(self):
        super().validate()
        _check_length_ns(f'{self.name!r} acquire_ns', self.acquire_ns)
        if int(self.window_start_ns) < 0 or int(self.window_len_ns) <= 0:
            raise ValueError(
                f"[opx] {self.name!r}: integration window start "
                f"{self.window_start_ns} ns / length {self.window_len_ns} ns "
                f"must be >= 0 / > 0.")
        if self.tail_ns < 0:
            raise ValueError(
                f"[opx] integration window (start {int(self.window_start_ns)} "
                f"ns + len {int(self.window_len_ns)} ns) does not fit in the "
                f"acquire window ({int(self.acquire_ns)} ns).")
        if self.weight == self.full_weight:
            raise ValueError(
                f"[opx] {self.name!r}: weight and full_weight must differ.")

    def apply_to_config(self, cfg) -> None:
        op = self.acquire_op
        e = {'digitalInputs': {'in': {'port': (self.con, int(self.marker_port)),
                                      'delay': 0, 'buffer': 0}},
             'outputs': {'out1': (self.con, int(self.in_port))},
             'time_of_flight': int(self.time_of_flight_ns),
             'smearing': 0}
        e.update(self._element_base())
        w = self.window()
        cfg['pulses'][self.pulse_name(op)] = {
            'operation': 'measurement',
            'length': int(self.acquire_ns),
            'digital_marker': self.marker_name(op),
            'integration_weights': {
                self.weight: self.weight_name(op, self.weight),
                self.full_weight: self.weight_name(op, self.full_weight),
            },
        }
        cfg['digital_waveforms'][self.marker_name(op)] = {'samples': [(1, 0)]}
        cfg['integration_weights'][self.weight_name(op, self.weight)] = {
            'cosine': w,
            'sine': [(0.0, ns) for _v, ns in w],
        }
        cfg['integration_weights'][self.weight_name(op, self.full_weight)] = {
            'cosine': [(1.0, int(self.acquire_ns))],
            'sine': [(0.0, int(self.acquire_ns))],
        }
        ctrl = _controller(cfg, self.con)
        ctrl.setdefault('analog_inputs', {})[int(self.in_port)] = {
            'offset': 0.0, 'gain_db': int(self.gain_db)}
        ctrl.setdefault('digital_outputs', {})[int(self.marker_port)] = {}
        cfg['elements'][self.name] = e


# ---------------------------------------------------------------------------
# root
# ---------------------------------------------------------------------------

@dataclass(kw_only=True)
class Machine:
    """The OPX as a list of elements (QUAM's QuamRoot, minus the tree
    magic). ``extra`` is free-form provenance the lab builder attaches
    (parameter values the config was compiled from, the handshake windows,
    ...); it must be JSON-able.

    generate_config(): the config template plus every element's slice, in
    list order, after validate(). to_dict(): JSON-able snapshot -- every
    element as asdict() + '__class__', plus the qm-qua version and a
    timestamp -- saved into the run file next to the QUA program text.
    """
    con: str = 'con1'
    controller_type: str = 'opx1'
    elements: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def names(self) -> tuple:
        return tuple(el.name for el in self.elements)

    def element(self, name) -> Element:
        for el in self.elements:
            if el.name == name:
                return el
        raise KeyError(
            f"[opx] no element {name!r} in the machine (has {self.names}).")

    def validate(self):
        seen = set()
        for el in self.elements:
            if not isinstance(el, Element):
                raise TypeError(
                    f"[opx] Machine.elements holds {type(el).__name__}, "
                    f"expected an Element.")
            if el.name in seen:
                raise ValueError(f"[opx] duplicate element name {el.name!r}.")
            seen.add(el.name)
            el.validate()
        # two elements driving one output port would fight (the APD marker
        # is on its own port for exactly this reason)
        for kind, attr in (('digital output', 'digital_output_ports'),
                           ('analog output', 'analog_output_ports')):
            owners = {}
            for el in self.elements:
                for port in getattr(el, attr):
                    key = (el.con, int(port))
                    if key in owners:
                        raise ValueError(
                            f"[opx] {kind} port {key} is driven by both "
                            f"{owners[key]!r} and {el.name!r}.")
                    owners[key] = el.name

    def generate_config(self) -> dict:
        self.validate()
        cfg = {
            'controllers': {self.con: {'type': self.controller_type}},
            'elements': {},
            'pulses': {},
            'waveforms': {},
            'digital_waveforms': {},
            'integration_weights': {},
        }
        for el in self.elements:
            el.apply_to_config(cfg)
        return cfg

    def to_dict(self) -> dict:
        els = []
        for el in self.elements:
            d = asdict(el)
            d['__class__'] = _class_path(el)
            els.append(d)
        return _plain({
            '__class__': _class_path(self),
            'con': self.con,
            'controller_type': self.controller_type,
            'elements': els,
            'extra': copy.deepcopy(self.extra),
            'qm_qua_version': qm_qua_version(),
            'generated': datetime.now().astimezone().isoformat(
                timespec='seconds'),
        })


def qm_qua_version():
    """Installed qm-qua version string, or None -- read from package
    metadata, so qm itself is never imported here."""
    try:
        from importlib.metadata import version
        return version('qm-qua')
    except Exception:
        return None
