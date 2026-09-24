"""ExptParams -> per-shot value tables for the OPX program.

Built once, after finish_prepare has repeated and shuffled the xvars: for
each flat shot index (nested-loop order, last xvar innermost -- exactly the
order the ARTIQ scan loop runs and the order OPX stream data comes back in),
set the xvar values on a working copy of ExptParams, run compute_derived()
and the experiment's compute_new_derived() exactly as the scan loop will,
and snapshot every scalar numeric attribute. Derived-of-xvar parameters
therefore vary per shot on the OPX by construction, not by a parallel
reimplementation.

Sequences never see this directly: ctx.p is a ParamsProxy whose attributes
are ParamRef handles -- per-shot columns that support ordinary arithmetic
(computed here on the host, shot by shot), resolved by the context into
either a baked constant (the value is the same every shot) or a QUA array
lookup (it varies). What a ParamRef can never become is one Python number:
the sequence body is traced once and the OPX replays it per shot, so
float()/int()/bool() -- and with them `if`, max(), np.sum() -- raise.
ctx.const(...) is the explicit way to read a parameter that is fixed for
the whole run.

Generic (future waxx.control.opx): no kexp imports, no qm imports.
"""

import copy
import numbers
import numpy as np


class ShotTables:
    """Per-shot host values, keyed by ExptParams attribute name.

    columns[key] is a float ndarray of length N_shots (execution order).
    """

    def __init__(self, columns, n_shots):
        self.columns = columns
        self.n_shots = int(n_shots)

    def has(self, key):
        return key in self.columns

    def column(self, key):
        return self.columns[key]

    def is_constant(self, key):
        col = self.columns[key]
        return bool(np.all(col == col[0]))


def as_host_scalar(x, what='value'):
    """A plain host number -> float; anything else is a clear TypeError.

    Arrays of more than one element are refused on purpose: an N_shots-long
    array would look like per-shot values, but nothing ties its order to the
    (shuffled) execution order the tables are in -- per-shot values come
    from ctx.p, or from a derived parameter, never from a loose array.
    """
    if isinstance(x, ParamRef):
        raise TypeError(
            f"[opx] {what} must be one number here, got the per-shot "
            f"parameter {x!r}. Use ctx.const(...) if it is fixed for the run.")
    if isinstance(x, (bool, np.bool_, numbers.Real)):
        return float(x)
    if (isinstance(x, np.ndarray) and x.size == 1
            and (np.issubdtype(x.dtype, np.number)
                 or np.issubdtype(x.dtype, np.bool_))):
        return float(x.reshape(()))
    raise TypeError(
        f"[opx] {what} must be a number or a ctx.p parameter, got "
        f"{type(x).__name__}: {x!r}")


def _fmt(v):
    return f"{float(v):g}"


# ufunc -> infix symbol for expression labels (error messages, warnings)
_BINARY_SYMBOLS = {
    np.add: '+', np.subtract: '-', np.multiply: '*', np.true_divide: '/',
    np.floor_divide: '//', np.remainder: '%', np.power: '**',
    np.less: '<', np.less_equal: '<=', np.greater: '>',
    np.greater_equal: '>=', np.equal: '==', np.not_equal: '!=',
}
_UNARY_SYMBOLS = {np.negative: '-', np.positive: '+'}


def _label(ufunc, labels):
    if ufunc in _BINARY_SYMBOLS and len(labels) == 2:
        return f"({labels[0]} {_BINARY_SYMBOLS[ufunc]} {labels[1]})"
    if ufunc in _UNARY_SYMBOLS and len(labels) == 1:
        return f"{_UNARY_SYMBOLS[ufunc]}{labels[0]}"
    if ufunc is np.absolute and len(labels) == 1:
        return f"abs({labels[0]})"
    return f"{ufunc.__name__}({', '.join(labels)})"


class ParamRef:
    """One per-shot column of host values -- what ctx.p.<name> hands out.

    Arithmetic with numbers and other ParamRefs (+ - * / // % **, unary -,
    abs, round, comparisons, and numpy ufuncs such as np.sin or np.maximum)
    yields a new ParamRef whose column is computed here, on the host, shot
    by shot -- exactly what a derived parameter in compute_new_derived
    does, without the detour. A context macro (ctx.raman_pulse, ctx.wait_s,
    ...) or ctx.cc()/ctx.hz()/ctx.f() then bakes it as a constant if every
    shot agrees, or as a QUA array lookup indexed by the shot counter if
    not. A comparison is a 0./1. column, usable as a per-shot factor; it is
    not something a Python `if` can branch on.

    A ParamRef is never one number. float()/int()/bool() -- and so `if`,
    max()/min(), `in`, np.sum()/np.mean() -- raise: the sequence body is
    traced once and the OPX replays it per shot, so any single value would
    be one shot's value baked into every shot, silently mislabeling the
    scan. ctx.const(ref) is the explicit way to read a parameter that is
    fixed for the whole run (a loop count, a toggle); it refuses one that
    varies.

    Loose arrays are refused as operands (see as_host_scalar).
    """

    def __init__(self, label, column, tables: ShotTables):
        self.label = str(label)
        col = np.asarray(column, dtype=float)
        if col.shape != (tables.n_shots,):
            raise ValueError(
                f"[opx] ParamRef {self.label!r}: column shape {col.shape} "
                f"does not match the run's {tables.n_shots} shots.")
        col = col.view()
        col.flags.writeable = False     # never a handle on the tables' data
        self._column = col
        self._tables = tables

    @property
    def column(self):
        """Host values per shot, execution order (read-only)."""
        return self._column

    @property
    def is_constant(self):
        c = self._column
        return bool(np.all(c == c[0]))

    def __repr__(self):
        c = self._column
        if self.is_constant:
            return f"ParamRef({self.label!r} = {_fmt(c[0])})"
        return (f"ParamRef({self.label!r}, per-shot: {_fmt(np.min(c))} .. "
                f"{_fmt(np.max(c))} over {c.size} shots)")

    # ------------------------------------------------------------------
    # refusals: a ParamRef is a column, never one number
    # ------------------------------------------------------------------

    def _per_shot_error(self, what, hint):
        return TypeError(
            f"[opx] {what} on ctx.p parameter {self.label!r}: the sequence "
            f"body is traced once and the OPX replays it per shot, so a "
            f"parameter is a per-shot column, not one number. {hint}")

    _HINT_NUMBER = (
        "Pass it to a ctx method (ctx.raman_pulse, ctx.wait_s, ...) or "
        "resolve it with ctx.cc/ctx.hz/ctx.f so the OPX reads the right "
        "value each shot; use ctx.const(...) only for a value that is fixed "
        "for the whole run.")
    _HINT_BRANCH = (
        "A Python `if` (or max/min/`in`) would pick one branch at trace time "
        "for every shot. Compute the per-shot value instead (np.maximum, "
        "np.minimum, a 0/1 comparison as a factor), or use "
        "ctx.const(...) for a run-level toggle.")

    def __float__(self):
        raise self._per_shot_error('float()', self._HINT_NUMBER)

    def __int__(self):
        raise self._per_shot_error('int()', self._HINT_NUMBER)

    def __index__(self):
        raise self._per_shot_error('int()', self._HINT_NUMBER)

    def __bool__(self):
        raise self._per_shot_error('bool()', self._HINT_BRANCH)

    # __eq__ is overridden below, which would otherwise drop __hash__
    __hash__ = object.__hash__

    # ------------------------------------------------------------------
    # arithmetic: column-wise on the host, via numpy's ufunc protocol
    # ------------------------------------------------------------------

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        if method != '__call__' or kwargs:
            raise self._per_shot_error(
                f"np.{ufunc.__name__}.{method}",
                "A reduction (np.sum, np.mean, ...) would collapse the shots "
                "of the scan into one number." if method != '__call__'
                else "Keyword arguments (out=, where=, ...) are not "
                     "supported on per-shot parameters.")
        if ufunc.nout != 1:
            raise TypeError(
                f"[opx] np.{ufunc.__name__} (multiple outputs) is not "
                f"supported on per-shot parameters.")
        cols, labels = [], []
        for x in inputs:
            if isinstance(x, ParamRef):
                if x._tables is not self._tables:
                    raise TypeError(
                        f"[opx] {x!r} and {self!r} belong to different "
                        f"runs' shot tables -- a sequence must only use the "
                        f"ctx.p it was called with.")
                cols.append(x._column)
                labels.append(x.label)
            else:
                v = as_host_scalar(x, f"operand of np.{ufunc.__name__}")
                cols.append(v)
                labels.append(_fmt(v))
        out = np.asarray(ufunc(*cols), dtype=float)    # bool -> 0./1.
        return ParamRef(_label(ufunc, labels), out, self._tables)

    def __add__(self, o): return np.add(self, o)
    def __radd__(self, o): return np.add(o, self)
    def __sub__(self, o): return np.subtract(self, o)
    def __rsub__(self, o): return np.subtract(o, self)
    def __mul__(self, o): return np.multiply(self, o)
    def __rmul__(self, o): return np.multiply(o, self)
    def __truediv__(self, o): return np.true_divide(self, o)
    def __rtruediv__(self, o): return np.true_divide(o, self)
    def __floordiv__(self, o): return np.floor_divide(self, o)
    def __rfloordiv__(self, o): return np.floor_divide(o, self)
    def __mod__(self, o): return np.remainder(self, o)
    def __rmod__(self, o): return np.remainder(o, self)
    def __pow__(self, o, mod=None): return np.power(self, o)
    def __rpow__(self, o): return np.power(o, self)
    def __neg__(self): return np.negative(self)
    def __pos__(self): return np.positive(self)
    def __abs__(self): return np.absolute(self)

    def __lt__(self, o): return np.less(self, o)
    def __le__(self, o): return np.less_equal(self, o)
    def __gt__(self, o): return np.greater(self, o)
    def __ge__(self, o): return np.greater_equal(self, o)
    def __eq__(self, o): return np.equal(self, o)
    def __ne__(self, o): return np.not_equal(self, o)

    def __round__(self, ndigits=None):
        return ParamRef(f"round({self.label}, {ndigits})",
                        np.round(self._column, ndigits or 0), self._tables)


class ParamsProxy:
    """What a sequence sees as ctx.p: attribute access -> ParamRef."""

    def __init__(self, tables: ShotTables):
        object.__setattr__(self, '_tables', tables)

    def __getattr__(self, key):
        if key.startswith('_'):
            raise AttributeError(key)
        if not self._tables.has(key):
            raise AttributeError(
                f"[opx] ExptParams has no scalar parameter {key!r} (arrays "
                f"and non-numeric attributes cannot be shipped per shot; "
                f"read fixed arrays from the experiment's params directly "
                f"when building the sequence).")
        return ParamRef(key, self._tables.column(key), self._tables)

    def __setattr__(self, key, value):
        raise AttributeError(
            "[opx] ctx.p is read-only: set parameters in prepare(), on the "
            "experiment's ExptParams.")

    def __dir__(self):
        return sorted(self._tables.columns)


def _snapshot_scalars(params, keys=None):
    """{key: float} of every scalar numeric attribute of a params object."""
    out = {}
    source = keys if keys is not None else vars(params).keys()
    for key in source:
        if key.startswith('_'):
            continue
        val = vars(params).get(key, None)
        if isinstance(val, (bool, np.bool_)):
            out[key] = float(val)
        elif isinstance(val, (int, float, np.integer, np.floating)):
            out[key] = float(val)
    return out


def build_shot_tables(expt) -> ShotTables:
    """Sweep the scan and tabulate every scalar param per shot.

    expt needs: xvardims, scan_xvars, params, compute_new_derived() -- i.e.
    any waxx Expt after finish_prepare. The experiment's live params object
    is swapped out for a working copy during the sweep (compute_new_derived
    operates on self.params/self.p) and restored afterwards, untouched.
    """
    xvardims = [int(d) for d in expt.xvardims]
    n_shots = int(np.prod(xvardims)) if xvardims else 1

    params_backup = expt.params
    work = copy.deepcopy(expt.params)
    expt.params = work
    if hasattr(expt, 'p'):
        expt.p = work

    try:
        columns = None
        keys = None
        flat = 0
        for idx in np.ndindex(*xvardims):
            for xvar, i in zip(expt.scan_xvars, idx):
                vars(work)[xvar.key] = xvar.values[i]
            work.compute_derived()
            expt.compute_new_derived()

            if columns is None:
                # key set frozen after the first shot's derived params exist
                keys = sorted(_snapshot_scalars(work).keys())
                columns = {k: np.empty(n_shots, dtype=float) for k in keys}
            snap = _snapshot_scalars(work, keys)
            for k in keys:
                columns[k][flat] = snap.get(k, np.nan)
            flat += 1
    finally:
        expt.params = params_backup
        if hasattr(expt, 'p'):
            expt.p = params_backup

    return ShotTables(columns, n_shots)
