"""Per-shot OPX sequences and their registry.

A sequence is the body of one experiment shot on the OPX -- everything
between the ARTIQ trigger and the hand-back. It is a plain Python function
of one argument (the OPXShotContext), expanded at trace time inside the
builder's shot loop; the builder owns the wait_for_trigger / RF-block
prologue and the hand-back epilogue, so a sequence cannot get the handoff
framing wrong.

The lab's sequences live in kexp/experiments/opx_sequences/ (import the
object and pass it to self.opx.use(...)); defining one inline in an
experiment file works identically since the decorator just returns the
OPXSequence object.

Data a sequence declares (all per shot):

    measurements={key: shape_spec}   streams the OPX saves into (ctx.measure,
                                     ctx.save, timestamp_key=...)
    host_data={key: shape_spec}      tables the host computed at trace time
                                     (ctx.host_data) -- what the OPX was
                                     given, recorded next to what it saved
    finish=callable(expt, data)      run after the containers are filled, to
                                     derive further containers on the host

A shape_spec is an int (n values per shot), a tuple (up to 2-D: DataVault
containers are 1-D/2-D), a Stream(shape, dtype) for an int stream
(timestamps, indices), or a callable of the live ExptParams returning one
of those (``lambda p: p.N_pulses``) -- resolved at use() with the run's
params, and checked again at finish_prepare against the same params.

Generic (future waxx.control.opx): no kexp imports, no qm imports.
"""

import numbers

import numpy as np

_REGISTRY = {}


def _as_dtype(dtype):
    """int | float | numpy int/float types | 'int' | 'float' -> int or float."""
    if dtype in (int, 'int') or (isinstance(dtype, type)
                                 and issubclass(dtype, np.integer)):
        return int
    if dtype in (float, 'float') or (isinstance(dtype, type)
                                     and issubclass(dtype, np.floating)):
        return float
    raise TypeError(f"[opx] stream dtype must be int or float, got {dtype!r}")


def _as_shape(shape, what='shape'):
    """int n -> (n,); tuple of positive ints (1-D or 2-D) -> tuple."""
    if isinstance(shape, (bool, np.bool_)):
        raise TypeError(f"[opx] {what} must be an int or a tuple, got {shape!r}")
    if isinstance(shape, (int, np.integer)):
        shape = (int(shape),)
    elif isinstance(shape, (tuple, list, np.ndarray)):
        shape = tuple(int(n) for n in shape)
    else:
        raise TypeError(
            f"[opx] {what} must be an int, a tuple of ints, a Stream, or a "
            f"callable of the params, got {type(shape).__name__}: {shape!r}")
    if not shape or len(shape) > 2:
        raise ValueError(
            f"[opx] {what} must be 1-D or 2-D (DataVault containers are), "
            f"got {shape}")
    if any(n < 1 for n in shape):
        raise ValueError(f"[opx] {what} must be positive per axis, got {shape}")
    return shape


class Stream:
    """Per-shot shape and dtype of one declared data key.

    Stream(4) == Stream((4,)) (float); Stream((N, m)) is a 2-D per-shot
    table; Stream(N, int) is an int stream (OPX timestamps in clock cycles,
    loop indices) -> int64 container, never volts-converted.
    """
    __slots__ = ('shape', 'dtype')

    def __init__(self, shape, dtype=float):
        self.shape = _as_shape(shape, 'Stream shape')
        self.dtype = _as_dtype(dtype)

    @property
    def n(self) -> int:
        """Saves per shot = prod(shape)."""
        return int(np.prod(self.shape))

    @property
    def np_dtype(self):
        return np.int64 if self.dtype is int else np.float64

    def __eq__(self, other):
        return (isinstance(other, Stream)
                and (self.shape, self.dtype) == (other.shape, other.dtype))

    def __hash__(self):
        return hash((self.shape, self.dtype))

    def __repr__(self):
        d = 'int' if self.dtype is int else 'float'
        return f"Stream({self.shape}, {d})"


def resolve_stream(spec, params=None, what='measurement') -> Stream:
    """A declared shape spec -> Stream. A callable is called with the live
    params (``lambda p: p.N_pulses``); without params that is an error."""
    if isinstance(spec, Stream):
        return spec
    if callable(spec):
        if params is None:
            raise RuntimeError(
                f"[opx] {what} shape is a callable of the params, but no "
                f"params were given to resolve it (use() resolves it with "
                f"the live ExptParams).")
        out = spec(params)
        if callable(out) and not isinstance(out, Stream):
            raise TypeError(f"[opx] {what} callable returned another "
                            f"callable: {out!r}")
        return resolve_stream(out, None, what)
    return Stream(_as_shape(spec, f'{what} shape'), float)


def _check_static_spec(spec, what):
    """Eager validation of what can be validated without params."""
    if isinstance(spec, Stream) or callable(spec):
        return
    _as_shape(spec, f'{what} shape')


class OPXSequence:
    """A named per-shot sequence.

    claims: channel roles this sequence uses (validated against the channel
        map at use(); ops on unclaimed roles are a trace-time error).
    measurements: {data_key: shape_spec} -- each key becomes an ordinary
        DataVault container of the per-shot shape (float64 for float
        streams, int64 for int streams), registered at use() so its shape
        flows into the run file like any other container. The traced body
        must save to each key exactly prod(shape) times per shot (saves
        inside ctx.for_range(n) count n times; a timestamp_key play/measure
        counts as one save on that key).
    host_data: {data_key: shape_spec} -- float64 containers filled at
        finish from the values the sequence handed to ctx.host_data(...) at
        trace time (per-shot tables the host drew and shipped to the OPX).
    finish: optional callable(expt, data) run after the containers are
        filled (derive containers from the raw saves). It must tolerate NaN
        rows: shots the OPX never ran are NaN (float) / -1 (int) and 0 in
        data.opx_data_valid.
    """

    def __init__(self, func, name=None, claims=(), measurements=None,
                 host_data=None, finish=None):
        self.func = func
        self.name = name or func.__name__
        self.claims = tuple(claims)
        self.measurements = dict(measurements or {})
        self.host_data = dict(host_data or {})
        self.finish = finish
        for key, spec in self.measurements.items():
            _check_static_spec(spec, f"sequence {self.name!r} "
                                     f"measurements[{key!r}]")
        for key, spec in self.host_data.items():
            _check_static_spec(spec, f"sequence {self.name!r} "
                                     f"host_data[{key!r}]")
        dup = set(self.measurements) & set(self.host_data)
        if dup:
            raise ValueError(
                f"[opx] sequence {self.name!r}: {sorted(dup)} declared both "
                f"as measurements and as host_data.")
        if finish is not None and not callable(finish):
            raise TypeError(
                f"[opx] sequence {self.name!r}: finish must be a "
                f"callable(expt, data), got {finish!r}")

    def resolve_measurements(self, params=None) -> dict:
        """{key: Stream} with any callable spec evaluated on params."""
        return {k: resolve_stream(v, params,
                                  f"sequence {self.name!r} measurements[{k!r}]")
                for k, v in self.measurements.items()}

    def resolve_host_data(self, params=None) -> dict:
        """{key: Stream} for the host-filled containers (float64 unless a
        Stream(..., int) was declared explicitly)."""
        return {k: resolve_stream(v, params,
                                  f"sequence {self.name!r} host_data[{k!r}]")
                for k, v in self.host_data.items()}

    def __call__(self, ctx):
        return self.func(ctx)

    def __repr__(self):
        extra = f", host_data={self.host_data}" if self.host_data else ''
        return (f"OPXSequence({self.name!r}, claims={self.claims}, "
                f"measurements={self.measurements}{extra})")


def opx_sequence(name=None, claims=(), measurements=None, host_data=None,
                 finish=None):
    """Decorator: wrap a per-shot function as a registered OPXSequence."""
    def wrap(func):
        seq = OPXSequence(func, name=name, claims=claims,
                          measurements=measurements, host_data=host_data,
                          finish=finish)
        if seq.name in _REGISTRY:
            print(f"[opx] WARNING: sequence {seq.name!r} re-registered "
                  f"(previous definition replaced).")
        _REGISTRY[seq.name] = seq
        return seq
    return wrap


def get_sequence(seq_or_name):
    """Resolve a sequence object or registered name to an OPXSequence.

    Name lookup only sees sequences whose module has been imported --
    prefer importing the object and passing it directly.
    """
    if isinstance(seq_or_name, OPXSequence):
        return seq_or_name
    if callable(seq_or_name):
        raise TypeError(
            f"[opx] {seq_or_name!r} is a bare function -- decorate it with "
            f"@opx_sequence(...) so its claims and measurements are declared.")
    try:
        return _REGISTRY[seq_or_name]
    except KeyError:
        raise KeyError(
            f"[opx] no sequence named {seq_or_name!r} is registered. "
            f"Registered: {sorted(_REGISTRY)}. Did you import its module "
            f"(kexp.experiments.opx_sequences.*)?")
