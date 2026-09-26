"""OPXProgramBuilder -- wraps a per-shot sequence in the run's shot loop.

The generated program is one job per run:

    latch sticky Raman analog drives (once; the intensity servo needs the
        AO drive never to drop) at amp(sqrt(power fraction)) -- see
        ChannelSpec.power_fraction_param
    for shot in range(N_shots):                # N = N_shots_with_repeats
        [re-point Raman IFs at this shot's transition, if it is scanned]
        wait_for_trigger                       # ARTIQ handoff (control.py)
        save(shot) -> opx_shot_index           # counter echo (see below)
        align                                  # A1: everything follows the trigger
        assert RF blocks on guarded channels   # 16 ns marker plays, sticky-held
        wait settle on every guarded switch    # settle = artiq_side + opx_side
        align                                  # A3: body starts after the settle
        <sequence body>                        # user code, params per shot
        hand-back: align (A4); trigger; hold blocks + drives
            t_handback_hold_s from the rising edge; release blocks
        [align (A5); restore Raman IFs -- only if the body moved a drive]
    ramp analog drives to zero                 # after the last shot's hold
    stream_processing: buffer per-shot saves (shape per declared key)

Handoff framing is owned here, not by sequences, so it cannot be gotten
wrong per experiment (the ARTIQ half is Control.handoff_to_quantum_machines
/ wait_for_quantum_machines_handback in kexp/base/control.py, which carries
the timing diagram). The contract, with today's ExptParams values:

    t = 0                 ARTIQ trigger edge (ttl32)
    t < artiq_side        OPX has seen the trigger and driven both RF blocks
                          HIGH (350 ns budget: trigger input latency + A1 +
                          one 16 ns marker play). THIS IS AN UNMEASURED
                          HARDWARE ASSUMPTION (milestone M1): if the OPX is
                          slower than t_opx_handoff_artiq_side, ARTIQ's RF
                          passes to the atoms until the block lands.
    t = artiq_side        ARTIQ turns its steady-state Raman + imaging RF on
                          and raises the handoff TTL (350 ns)
    t = artiq_side
        + opx_side        ARTIQ returns to the caller (1.35 us); the OPX body
                          may start: settle = artiq_side + opx_side is what
                          ChannelMap.t_handoff_settle_s holds (the lab map
                          fills it with that sum) and what the builder waits
                          after the block plays
    t_e                   OPX hand-back trigger, rising edge (any time after
                          the settle; a body with nothing to play hands back
                          within a microsecond -- ARTIQ arms its gate before
                          the trigger, so no minimum shot length is imposed)
    t_e + receive         ARTIQ timestamps the edge
                          (t_opx_handback_artiq_trigger_receive_latency, 1 us)
    t_e + receive + rtio  ARTIQ switch-only take-back: RF off, handoff TTL
                          low (t_opx_handback_artiq_rtio_delay after its
                          timestamp, 2 us)
    t_e + hold            = + t_opx_handback_switch_fall_delay (2 us): those
                          switches have fallen. OPX releases the blocks
                          (pass); only from here may it touch its analog
                          drives (ramp_to_zero after the final shot, IF
                          re-points) -- they wait with the blocks. ARTIQ's
                          timeline resumes. hold = receive + rtio + fall =
                          ChannelMap.t_handback_hold_s (5 us)

* The switch elements are sticky-digital. The OPX program itself releases
  the blocks at t_e + hold regardless of what ARTIQ does; a crash on the
  ARTIQ side mid-window therefore ends with the blocks released and
  ARTIQ's RF still ON on both switch AOMs (handoff TTL HIGH) until
  cleanup_scan_kernel / the next init_kernel turns them off. A job halted
  mid-block (the OPX side crashing) is the case the M1 scope check must
  settle: what the digital lines do after job.halt is not documented.
* Between shots every block is released (pass), so ARTIQ gates its own
  light for preparation and camera imaging exactly as in a non-OPX run.

Shot-index echo: the loop counter is saved once per shot into the stream
'opx_shot_index'. ARTIQ and the OPX visit shots in the same order only by
construction (one trigger per scan_kernel); the echo lets fill_containers
verify the stream really holds shots 0, 1, 2, ... and cut the valid mask at
the first mismatch instead of silently mislabeling data.

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

import numpy as np

from kexp.control.opx.context import OPXShotContext
from kexp.control.opx.sequence import Stream
from kexp.control.opx.units import s_to_cc, MAX_ANALOG_V, QUA_AMP_LIMIT
from kexp.control.opx.trace_log import (OpLog, PHASE_PROLOGUE,
                                        PHASE_HANDSHAKE, PHASE_EPILOGUE)

if TYPE_CHECKING:
    # static-analysis only -- qm must not import at runtime until trace()
    from qm.program import Program

# stream / container key of the per-shot loop-counter echo (int, 1/shot)
SHOT_INDEX_KEY = 'opx_shot_index'
SHOT_INDEX_STREAM = Stream((1,), int)
# every stream the builder itself saves (a sequence may not declare these)
RESERVED_STREAMS = {SHOT_INDEX_KEY: SHOT_INDEX_STREAM}


class _TablesParamsView:
    """Stand-in params for resolving callable shape specs when no live
    params object is given: attribute -> the run-constant value of that
    column (a varying column is refused, as ctx.const would)."""

    def __init__(self, tables):
        object.__setattr__(self, '_tables', tables)

    def __getattr__(self, key):
        t = self._tables
        if key.startswith('_') or not t.has(key):
            raise AttributeError(
                f"[opx] shape spec reads params.{key}, which is not a scalar "
                f"parameter of the run.")
        col = t.column(key)
        if not t.is_constant(key):
            raise RuntimeError(
                f"[opx] shape spec reads params.{key}, which varies per "
                f"shot ({np.min(col):g} .. {np.max(col):g}); a per-shot "
                f"data shape must be fixed for the run.")
        v = float(col[0])
        return int(v) if v == int(v) else v


class OPXProgramBuilder:

    def __init__(self, sequence, channel_map, tables, n_shots, params=None):
        self.sequence = sequence
        self.map = channel_map
        self.tables = tables
        self.n_shots = int(n_shots)
        self.log: 'OpLog | None' = None   # filled by trace()
        self.skip_triggers = False
        # declared per-shot shapes, resolved against the live params (the
        # manager passes expt.params); without them, against the tables
        p = params if params is not None else _TablesParamsView(tables)
        self.measurements = sequence.resolve_measurements(p)
        self.host_data = sequence.resolve_host_data(p)
        self.echo_stream = None

    def stream_specs(self) -> dict:
        """{key: Stream} of every stream the program saves: the declared
        measurements plus the shot-index echo."""
        out = dict(self.measurements)
        out.update(RESERVED_STREAMS)
        return out

    def _latch_scale(self, ctx, role, spec):
        """(power fraction, amp() factor) a role's analog drives latch at:
        (f, sqrt(f)) for f = ctx.p.<spec.power_fraction_param> -- power goes
        as amplitude^2, and the config amplitude is fraction 1 -- or
        (None, None) for a role without one (latched at the config
        amplitude).

        Read through ctx.p, so the parameter is recorded as accessed and
        the Adjust panel refuses it. The drives latch once per run, so a
        fraction that varies per shot is refused rather than silently
        latched at its first value. When the map carries a machine, the
        latched amplitude is checked against the analog output limit.
        """
        key = getattr(spec, 'power_fraction_param', None)
        if key is None:
            return None, None
        ref = getattr(ctx.p, key)
        col = ref.column
        bad = ~(np.isfinite(col) & (col >= 0.))
        if np.any(bad):
            raise ValueError(
                f"[opx] {key} = {float(col[bad][0])!r}: a power fraction must be a "
                f"finite number >= 0.")
        if not ref.is_constant:
            raise RuntimeError(
                f"[opx] {key!r} varies per shot ({np.min(col):g} .. "
                f"{np.max(col):g}), but the {role!r} analog drives latch once "
                f"per run at amp(sqrt({key})) -- every shot would run at the "
                f"first value. Take one run per value.")
        fraction = float(col[0])
        scale = float(np.sqrt(fraction))
        if not scale < QUA_AMP_LIMIT:
            raise ValueError(
                f"[opx] {key} = {fraction:g} needs amp({scale:g}) on the "
                f"{role!r} latch, outside QUA's amp() range "
                f"[-{QUA_AMP_LIMIT:g}, {QUA_AMP_LIMIT:g}).")
        machine = getattr(self.map, 'machine', None)
        if machine is not None:
            for el in spec.analog_elements:
                a = getattr(machine.element(el), 'amplitude_v', None)
                if a is not None and abs(a * scale) > MAX_ANALOG_V:
                    raise ValueError(
                        f"[opx] {key} = {fraction:g} latches {el!r} at "
                        f"{a:g} V x {scale:g} = {a * scale:g} V, above the "
                        f"analog output limit of {MAX_ANALOG_V:g} V.")
        return fraction, scale

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
        guarded_switches = [s.switch_element for s in guarded_specs]
        sync_el = cmap.spec(cmap.sync_channel).switch_element
        settle_cc = s_to_cc(cmap.t_handoff_settle_s,
                            key='t_handoff_settle_s')
        hold_cc = s_to_cc(cmap.t_handback_hold_s, key='t_handback_hold_s')

        log = OpLog(seq.func, self.tables.n_shots)
        self.log = log
        self.skip_triggers = bool(skip_triggers)

        with qua.program() as prog:
            shot = qua.declare(int)
            echo = qua.declare_output_stream()
            self.echo_stream = echo
            ctx = OPXShotContext(cmap, self.tables, seq, shot,
                                 hold_cc, guarded_specs, log=log,
                                 measurements=self.measurements,
                                 host_data=self.host_data)

            # run prologue: latch the sticky analog drives once. Sticky
            # plays accumulate on the held value, so this is the only place
            # they are played (per-shot re-latching would add amplitudes).
            # A role with a power_fraction_param latches at
            # amp(sqrt(fraction)) of the config (fraction-1) amplitude.
            log.new_call('latch')
            for role in seq.claims:
                spec = cmap.spec(role)
                if not spec.analog_elements:
                    continue
                fraction, scale = self._latch_scale(ctx, role, spec)
                for el in spec.analog_elements:
                    if scale is None:
                        log.record('play', el, spec.analog_latch_op,
                                   phase=PHASE_PROLOGUE, macro='latch',
                                   note=f'{role} analog drive latched '
                                        f'(sticky: holds for the whole run)')
                        qua.play(spec.analog_latch_op, el)
                        continue
                    key = spec.power_fraction_param
                    log.record('play', el, spec.analog_latch_op,
                               phase=PHASE_PROLOGUE, macro='latch',
                               label=f'sqrt({key})',
                               note=f'{role} analog drive latched at '
                                    f'amp({scale:.6g}) = sqrt({key} = '
                                    f'{fraction:g}) of the config amplitude '
                                    f'(sticky: holds for the whole run)',
                               amp_scale=scale, power_fraction=fraction,
                               power_fraction_param=key)
                    qua.play(spec.analog_latch_op * qua.amp(scale), el)

            # analog drives that follow a transition parameter: the config
            # IFs are the first shot's value; when it varies, re-point the
            # drives at the top of every shot -- right after the previous
            # hand-back's hold (the drives wait it out with the blocks), while
            # ARTIQ owns the AOs and prepares the shot, so the new tone is
            # long settled by the trigger
            transitions = {}
            for role in seq.claims:
                spec = cmap.spec(role)
                if spec.transition_to_ifs is not None:
                    transitions[role] = getattr(ctx.p, spec.transition_param)

            with qua.for_(shot, 0, shot < self.n_shots, shot + 1):
                for role, base in transitions.items():
                    if not base.is_constant:
                        ctx._point_transition(role, base, macro='transition',
                                              phase=PHASE_HANDSHAKE)
                log.new_call('handoff')
                if not skip_triggers:
                    log.record('wait_for_trigger', sync_el,
                               phase=PHASE_HANDSHAKE, macro='handoff',
                               note='park until the ARTIQ trigger')
                    qua.wait_for_trigger(sync_el)
                # counter echo: which shot the OPX thinks this is
                log.record('save', None, phase=PHASE_HANDSHAKE,
                           macro='handoff', data_key=SHOT_INDEX_KEY,
                           note='shot counter echoed to the host (order '
                                'check at fill time)')
                qua.save(shot, echo)
                # A1: nothing runs ahead of the trigger
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
                # ARTIQ's RF comes on at artiq_side and the kernel returns
                # at artiq_side + opx_side = settle: nothing exposes before
                # then. Waited on every guarded switch (they were aligned
                # by A1 and the block plays are equal-length), then one
                # align brings the drives and detector to the body start.
                log.record('wait', guarded_switches[0], phase=PHASE_HANDSHAKE,
                           macro='handoff', label='t_handoff_settle_s',
                           duration_cc=settle_cc, values=settle_cc * 4e-9,
                           elements=list(guarded_switches),
                           note='ARTIQ RF on at artiq_side, settled by '
                                'artiq_side + opx_side')
                qua.wait(settle_cc, *guarded_switches)
                # A3
                log.record('align', None, phase=PHASE_HANDSHAKE,
                           macro='handoff')
                qua.align()

                seq.func(ctx)

                if not ctx._handback_done:
                    ctx.handback_to_artiq()
                # the body moved a drive off the run's transition (Ramsey
                # detuning, ...): point it back so the next shot starts
                # there. A varying transition is re-pointed at the top of
                # the next shot anyway. A5 (align) only when needed: the
                # update must follow the hand-back on the drives' own
                # timelines, whose cursor otherwise sits at the last align.
                restore = [role for role in sorted(ctx._if_touched)
                           if transitions.get(role) is not None
                           and transitions[role].is_constant]
                if restore:
                    log.new_call('shot_end')
                    log.record('align', None, phase=PHASE_HANDSHAKE,
                               macro='handback')
                    qua.align()
                    for role in restore:
                        ctx._point_transition(role, transitions[role],
                                              macro='transition_restore',
                                              phase=PHASE_HANDSHAKE)

            # run epilogue: analog drives down; blocks were already released
            # to pass in the final shot's hand-back. The drives waited out
            # that hand-back's hold with the blocks, so the ramp starts
            # t_handback_hold_s after the last trigger edge, once ARTIQ has
            # dropped the handoff TTL and has the AOs back.
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

            with qua.stream_processing():
                for key, stream in ctx._streams.items():
                    spec = self.measurements[key]
                    st = stream
                    # (n1, n2) per shot -> buffer(n2).buffer(n1): the saves
                    # come row-major, the inner buffer groups a row
                    for n in reversed(spec.shape):
                        st = st.buffer(int(n))
                    st.save_all(key)
                echo.save_all(SHOT_INDEX_KEY)

        self._validate(ctx)
        return prog, ctx

    def _validate(self, ctx):
        seq = self.sequence
        for key, spec in self.measurements.items():
            n_traced = ctx._save_counts.get(key, 0)
            if n_traced != spec.n:
                raise RuntimeError(
                    f"[opx] sequence {seq.name!r} declares {spec.n} "
                    f"saves per shot into {key!r} (shape {spec.shape}) but "
                    f"the traced body performs {n_traced} (saves inside "
                    f"ctx.for_range(n) count n times; a timestamp_key "
                    f"play/measure counts once). The data container shape "
                    f"comes from the declaration -- make them agree.")
        for key in self.host_data:
            if key not in ctx._host_data_values:
                raise RuntimeError(
                    f"[opx] sequence {seq.name!r} declares host_data "
                    f"{key!r} but never wrote it with ctx.host_data({key!r}, "
                    f"values).")
