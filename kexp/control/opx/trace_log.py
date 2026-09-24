"""Trace-time op log -- provenance for every QUA statement the builder emits.

The sequence body is traced once; every ``qua.play`` / ``wait`` / ``measure``
/ ``align`` the context or builder emits is also appended here as an
``OpRecord``: which element and operation, the requested duration per shot
(clock cycles, host-side), on which shots it actually executes (a per-shot
``if_`` guard), which *macro* produced it (``raman_pulse``, ``wait_s``,
``measure``, the handshake framing), the parameter expression it came from
(``t_raman_pulse``, ``(t_raman_pi_pulse / 2)``) with its per-shot values,
and the source file / line chain in the sequence code that called it.

Nothing here changes the program: the log is read after the fact by the
pulse viewer (``kexp.control.opx.viewer``), which matches it against the
simulator's waveform report so every simulated pulse points back at the
line of Python -- and the line of generated QUA -- that made it.

Generic (future waxx.control.opx): no kexp imports, no qm imports.
"""

import inspect
import linecache
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# statement kinds, one per QUA call the builder/context can emit; the QUA
# line mapper matches these against the serialized program text
KINDS = ('play', 'wait', 'align', 'measure', 'save', 'wait_for_trigger',
         'ramp_to_zero', 'reset_if_phase', 'reset_frame', 'update_frequency',
         'frame_rotation_2pi', 'if')

# kinds that show up as a point event marker on an analog lane (no pulse)
EVENT_KINDS = ('reset_if_phase', 'reset_frame', 'update_frequency',
               'frame_rotation_2pi')

# phases of the run the builder frames each shot with
PHASE_PROLOGUE = 'prologue'      # once per run, before the shot loop
PHASE_HANDSHAKE = 'handshake'    # per shot, builder-owned framing
PHASE_BODY = 'body'              # per shot, the sequence's own code
PHASE_EPILOGUE = 'epilogue'      # once per run, after the loop


@dataclass
class SourceRef:
    """Where in the sequence code an op came from.

    lines: innermost first -- the line that emitted the op, then each caller
    up to (and including) the sequence function itself, all within the
    sequence's source file. Helper functions in the same file show up as
    extra entries.
    """
    file: str
    lines: list
    function: str = ''

    @property
    def line(self) -> int:
        return int(self.lines[0]) if self.lines else 0


@dataclass
class OpRecord:
    index: int                       # emission order, 0-based
    kind: str                        # one of KINDS
    element: Optional[str]           # QUA element (None for align/if)
    op: Optional[str] = None         # operation name on the element
    phase: str = PHASE_BODY
    macro: str = ''                  # ctx method / builder step that emitted it
    label: str = ''                  # parameter expression label, if any
    # requested duration per shot in clock cycles (None: the pulse's config
    # length); a scalar means the same on every shot
    duration_cc: Optional[np.ndarray] = None
    # per-shot host values of the parameter behind `label` (SI), if any
    values: Optional[np.ndarray] = None
    # True on the shots this op executes (a per-shot if_ guard); None = all
    executes: Optional[np.ndarray] = None
    source: Optional[SourceRef] = None
    data_key: str = ''               # measurement data key, for measure/save
    note: str = ''                   # free text for the viewer's tooltip
    call: int = 0                    # groups the records of one macro call
    extra: dict = field(default_factory=dict)

    def executes_on(self, shot) -> bool:
        if self.executes is None:
            return True
        return bool(self.executes[int(shot)])

    def duration_on(self, shot):
        """Requested duration on `shot` in clock cycles, or None."""
        if self.duration_cc is None:
            return None
        d = np.atleast_1d(self.duration_cc)
        return int(d[int(shot)] if d.size > 1 else d[0])

    def value_on(self, shot):
        if self.values is None:
            return None
        v = np.atleast_1d(self.values)
        return float(v[int(shot)] if v.size > 1 else v[0])


class OpLog:
    """The ordered list of emitted ops for one traced program."""

    def __init__(self, sequence_func=None, n_shots=1):
        self.records: list[OpRecord] = []
        self.n_shots = int(n_shots)
        self._seq_func = sequence_func
        self._seq_file = None
        self._seq_code = None
        if sequence_func is not None:
            code = getattr(sequence_func, '__code__', None)
            self._seq_code = code
            self._seq_file = code.co_filename if code is not None else None
        self.source_text: Optional[str] = None
        self.source_first_line: int = 1
        self.source_path: Optional[str] = None
        self._capture_source()
        self._call = 0
        self.calls: dict[int, str] = {}   # call id -> macro name

    def new_call(self, macro) -> int:
        """Start a new macro-call group: every record until the next
        new_call() belongs to it (the viewer draws one step bar per group)."""
        self._call += 1
        self.calls[self._call] = str(macro)
        return self._call

    # ------------------------------------------------------------------
    # source text of the sequence
    # ------------------------------------------------------------------

    def _capture_source(self):
        """The text the source refs point into: the whole file when it is a
        real file, otherwise (a notebook cell) just the function's own
        source with its first line number, from IPython's linecache."""
        func = self._seq_func
        if func is None:
            return
        path = self._seq_file
        self.source_path = path
        try:
            lines = linecache.getlines(path) if path else []
        except Exception:
            lines = []
        if lines:
            self.source_text = ''.join(lines)
            self.source_first_line = 1
            return
        try:
            src_lines, first = inspect.getsourcelines(func)
            self.source_text = ''.join(src_lines)
            self.source_first_line = int(first)
        except (OSError, TypeError):
            self.source_text = None

    # ------------------------------------------------------------------
    # recording
    # ------------------------------------------------------------------

    def capture_source(self, skip=2) -> Optional[SourceRef]:
        """Walk the stack from the caller outward and collect every frame
        that lives in the sequence's source file, stopping at (and
        including) the sequence function's own frame. None when the op was
        not emitted from sequence code (builder-owned framing)."""
        if self._seq_file is None:
            return None
        f = sys._getframe(skip)
        lines, func_name, reached = [], '', False
        while f is not None:
            code = f.f_code
            if code.co_filename == self._seq_file:
                lines.append(int(f.f_lineno))
                if not func_name:
                    func_name = code.co_name
                if code is self._seq_code:
                    reached = True
                    break
            f = f.f_back
        if not reached:
            # not called from inside the sequence body (module-level code in
            # the same file, or the builder's own framing)
            return None
        return SourceRef(self._seq_file, lines, func_name)

    def record(self, kind, element=None, op=None, phase=PHASE_BODY, macro='',
               label='', duration_cc=None, values=None, executes=None,
               source=None, data_key='', note='', capture=True, **extra
               ) -> OpRecord:
        if kind not in KINDS:
            raise ValueError(f"[opx] unknown op kind {kind!r}")
        if source is None and capture and phase == PHASE_BODY:
            source = self.capture_source(skip=2)
        rec = OpRecord(
            index=len(self.records), kind=kind, element=element, op=op,
            phase=phase, macro=macro, label=label,
            duration_cc=(None if duration_cc is None
                         else np.atleast_1d(np.asarray(duration_cc))),
            values=(None if values is None
                    else np.atleast_1d(np.asarray(values, dtype=float))),
            executes=(None if executes is None
                      else np.atleast_1d(np.asarray(executes, dtype=bool))),
            source=source, data_key=data_key, note=note, call=self._call,
            extra=dict(extra))
        self.records.append(rec)
        return rec

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def __len__(self):
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    def of_kind(self, *kinds):
        return [r for r in self.records if r.kind in kinds]

    def for_element(self, element):
        return [r for r in self.records if r.element == element]
