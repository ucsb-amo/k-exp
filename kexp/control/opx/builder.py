"""OPXProgramBuilder -- wraps a per-shot sequence in the run's shot loop.

The generated program is one job per run:

    latch sticky Raman analog drives (once; the intensity servo needs the
        AO drive never to drop)
    for shot in range(N_shots):                # N = N_shots_with_repeats
        wait_for_trigger                       # ARTIQ handoff (control.py)
        assert RF blocks on guarded channels   # within ~100 ns of the trigger
        wait t_opx_handoff_settle              # ARTIQ RF on at settle/2, settled by settle
        <sequence body>                        # user code, params per shot
        hand-back trigger; hold blocks for t_opx_handback_overlap; release
    ramp analog drives to zero
    stream_processing: buffer per-shot saves

Handoff framing is owned here, not by sequences, so it cannot be gotten
wrong per experiment (the ARTIQ half is Control.handoff_to_quantum_machines
/ wait_for_quantum_machines_handback in kexp/base/control.py, which carries
the timing diagram):

* The blocks go up within ~a hundred ns of the trigger. ARTIQ turns its
  steady-state RF on t_opx_handoff_settle/2 after the trigger, and the body
  only starts t_opx_handoff_settle after it, so no exposure runs before the
  RF is on and settled. The two timing numbers come from ExptParams through
  the channel map -- the same source control.py reads.
* The hand-back edge may come any time after the trigger (a body with
  nothing to play hands back within a microsecond): ARTIQ arms its gate
  before triggering, so no minimum shot length is imposed here.
* The switch elements are sticky-digital: an ARTIQ crash mid-window (no
  ARTIQ cleanup runs) leaves the blocks HIGH, and the light off the atoms,
  until the ARTIQ process exits. The manager then halts the job and the OPX
  lines idle low (pass), so whatever ARTIQ RF was on passes until the next
  run's init_kernel or a Monitor restart -- the same end state as any crash
  with a beam on. (A block left stuck high would instead silently darken
  every following non-OPX run.)
* Between shots every block is released (pass), so ARTIQ gates its own
  light for preparation and camera imaging exactly as in a non-OPX run.

Future extensions plug in here (see on_finish_prepare in manager.py for the
other half):
* input-stream parameter delivery (qua.declare_input_stream +
  advance_input_stream at the top of the loop, values pushed per shot from
  an ARTIQ RPC) -- swap the ParamRef materialization in context._resolve;
  the sequence API does not change.
* a second mid-shot ARTIQ -> OPX sync would be another wait_for_trigger
  exposed as a ctx macro, once the hardware line for it exists.

Generic (future waxx.control.opx): no kexp imports; qm imported inside
methods only.
"""

from typing import TYPE_CHECKING

from kexp.control.opx.context import OPXShotContext
from kexp.control.opx.units import s_to_cc
from kexp.control.opx.trace_log import (OpLog, PHASE_PROLOGUE,
                                        PHASE_HANDSHAKE, PHASE_EPILOGUE)

if TYPE_CHECKING:
    # static-analysis only -- qm must not import at runtime until trace()
    from qm.program import Program


class OPXProgramBuilder:

    def __init__(self, sequence, channel_map, tables, n_shots):
        self.sequence = sequence
        self.map = channel_map
        self.tables = tables
        self.n_shots = int(n_shots)
        self.log: 'OpLog | None' = None   # filled by trace()
        self.skip_triggers = False

    def trace(self, skip_triggers=False
              ) -> 'tuple[Program, OPXShotContext]':
        """Build the QUA program. Returns (program, context) -- the context
        carries the stream handles and per-key roles the manager needs.

        skip_triggers=True omits the per-shot wait_for_trigger, for the QOP
        simulator only: it has no external trigger source, so a simulated
        program would park on the first wait forever (00d guards it out the
        same way). Shots then run back-to-back on the simulated timeline.
        The real (execute/provenance) program always keeps its triggers.
        """
        from qm import qua

        seq = self.sequence
        cmap = self.map

        # every channel the ARTIQ handoff kernel turns RF on for is guarded,
        # claimed or not; claimed channels beyond that are guarded too
        guard_roles = list(cmap.guarded_channels)
        for role in seq.claims:
            if role not in guard_roles:
                guard_roles.append(role)
        guarded_specs = [cmap.spec(r) for r in guard_roles]
        sync_el = cmap.spec(cmap.sync_channel).switch_element
        settle_cc = s_to_cc(cmap.t_handoff_settle_s,
                            key='t_opx_handoff_settle')
        overlap_cc = s_to_cc(cmap.t_handback_overlap_s,
                             key='t_opx_handback_overlap')

        log = OpLog(seq.func, self.tables.n_shots)
        self.log = log
        self.skip_triggers = bool(skip_triggers)

        with qua.program() as prog:
            shot = qua.declare(int)
            ctx = OPXShotContext(cmap, self.tables, seq, shot,
                                 overlap_cc, guarded_specs, log=log)

            # run prologue: latch the sticky analog drives once. Sticky
            # plays accumulate on the held value, so this is the only place
            # they are played (per-shot re-latching would add amplitudes).
            log.new_call('latch')
            for role in seq.claims:
                spec = cmap.spec(role)
                for el in spec.analog_elements:
                    log.record('play', el, spec.analog_latch_op,
                               phase=PHASE_PROLOGUE, macro='latch',
                               note=f'{role} analog drive latched (sticky: '
                                    f'holds for the whole run)')
                    qua.play(spec.analog_latch_op, el)

            with qua.for_(shot, 0, shot < self.n_shots, shot + 1):
                log.new_call('handoff')
                if not skip_triggers:
                    log.record('wait_for_trigger', sync_el,
                               phase=PHASE_HANDSHAKE, macro='handoff',
                               note='park until the ARTIQ trigger')
                    qua.wait_for_trigger(sync_el)
                log.record('align', None, phase=PHASE_HANDSHAKE,
                           macro='handoff')
                qua.align()
                # blocks up before ARTIQ turns its RF steady-state on
                for spec in guarded_specs:
                    log.record('play', spec.switch_element, spec.block_op,
                               phase=PHASE_HANDSHAKE, macro='handoff',
                               note='RF blocked before ARTIQ turns its '
                                    'steady-state RF on')
                    qua.play(spec.block_op, spec.switch_element)
                log.record('align', None, phase=PHASE_HANDSHAKE,
                           macro='handoff')
                qua.align()
                # ARTIQ's RF comes on at settle/2 and is settled by settle:
                # nothing exposes before then (control.py timing diagram)
                log.record('wait', sync_el, phase=PHASE_HANDSHAKE,
                           macro='handoff', label='t_opx_handoff_settle',
                           duration_cc=settle_cc, values=settle_cc * 4e-9,
                           note='ARTIQ RF on at settle/2, settled by settle')
                qua.wait(settle_cc, sync_el)
                log.record('align', None, phase=PHASE_HANDSHAKE,
                           macro='handoff')
                qua.align()

                seq.func(ctx)

                if not ctx._handback_done:
                    ctx.handback_to_artiq()
                log.new_call('shot_end')
                log.record('align', None, phase=PHASE_HANDSHAKE,
                           macro='handback')
                qua.align()

            # run epilogue: analog drives down; blocks were already released
            # to pass in the final shot's hand-back
            log.new_call('epilogue')
            for role in seq.claims:
                spec = cmap.spec(role)
                for el in spec.analog_elements:
                    log.record('ramp_to_zero', el, phase=PHASE_EPILOGUE,
                               macro='epilogue',
                               note=f'{role} analog drive ramped to zero')
                    qua.ramp_to_zero(el)
            log.record('align', None, phase=PHASE_EPILOGUE, macro='epilogue')
            qua.align()

            if ctx._streams:
                with qua.stream_processing():
                    for key, (stream, _ivar) in ctx._streams.items():
                        n_per_shot = seq.measurements[key]
                        stream.buffer(n_per_shot).save_all(key)

        self._validate(ctx)
        return prog, ctx

    def _validate(self, ctx):
        seq = self.sequence
        for key, n_declared in seq.measurements.items():
            n_traced = ctx._save_counts.get(key, 0)
            if n_traced != n_declared:
                raise RuntimeError(
                    f"[opx] sequence {seq.name!r} declares {n_declared} "
                    f"saves per shot into {key!r} but the traced body "
                    f"performs {n_traced}. The data container shape comes "
                    f"from the declaration -- make them agree.")
