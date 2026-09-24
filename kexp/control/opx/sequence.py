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

Generic (future waxx.control.opx): no kexp imports, no qm imports.
"""

_REGISTRY = {}


class OPXSequence:
    """A named per-shot sequence.

    claims: channel roles this sequence uses (validated against the channel
        map at use(); ops on unclaimed roles are a trace-time error).
    measurements: {data_key: N_per_shot} -- each key becomes an ordinary
        DataVault container of per-shot shape (N,), registered at use() time
        so its shape flows into the run file like any other container. The
        traced body must save to each key exactly N times per shot.
    """

    def __init__(self, func, name=None, claims=(), measurements=None):
        self.func = func
        self.name = name or func.__name__
        self.claims = tuple(claims)
        self.measurements = dict(measurements or {})
        for key, n in self.measurements.items():
            if not (isinstance(n, int) and n >= 1):
                raise ValueError(
                    f"[opx] sequence {self.name!r}: measurements[{key!r}] "
                    f"must be a positive int (saves per shot), got {n!r}")

    def __call__(self, ctx):
        return self.func(ctx)

    def __repr__(self):
        return (f"OPXSequence({self.name!r}, claims={self.claims}, "
                f"measurements={self.measurements})")


def opx_sequence(name=None, claims=(), measurements=None):
    """Decorator: wrap a per-shot function as a registered OPXSequence."""
    def wrap(func):
        seq = OPXSequence(func, name=name, claims=claims,
                          measurements=measurements)
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
