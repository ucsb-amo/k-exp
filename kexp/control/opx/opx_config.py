"""K-machine OPX+ wiring: the component machine (QUA config) from ExptParams
+ dds defaults, the channel role map, and the manager factory Base uses.

This is the lab-specific half of kexp.control.opx (the dds_frame analog for
the OPX). Everything physical lives here: ports, element names, polarities,
and which ExptParams / dds defaults feed which config value. The elements
are kexp.control.opx.components instances (build_machine); the config dict
is generated from them (build_opx_config) and the machine itself travels on
ChannelMap.machine so the manager can save machine.to_dict() as run
provenance next to the QUA program text.

Config-time vs shot-time: values in this file are compiled into the QUA
config ONCE per run (analog drive frequencies/amplitudes, acquire and
integration windows, the handshake windows). They cannot be xvars or
live-adjusted -- CONFIG_TIME_PARAMS lists the ExptParams keys concerned;
they are recorded as accessed on the shot tables (so the Adjust-panel
guard covers them), a scan of one raises here, and the manager refuses them
as xvars (design D2). Pulse durations, detunings and phases are shot-time
and scan freely. The Raman drive IFs have that route built in: they follow
frequency_raman_transition (split by expt.raman, the ARTIQ RamanBeamPair),
compiled at the first executed shot's value and updated per shot by the
builder when it is scanned.

Hardware truth table (2026-09, from the switch-box wiring):

    OPX raman-switch TTL   (digital 1): low = ARTIQ RF passes to the common
                                        Raman switch AOM, high = blocked
    OPX imaging-switch TTL (digital 2): same, for the imaging switch AOM
    OPX hand-back trigger  (digital 3): -> ttl.quantum_machines_receive_trigger
    ARTIQ raman-RF-handoff TTL: low = raman 80/150 AOs driven by ARTIQ DDS,
                                high = driven by OPX analog outs 1/2

The OPX digital lines idle low (= pass) when no job runs, so ARTIQ gates its
own light whenever the OPX is out of the picture.
"""

import numpy as np

from kexp.config.ip import QM_OPX_IP, QM_OPX_CLUSTER
from kexp.config.expt_params import ExptParams
from kexp.control.opx.channels import ChannelMap, ChannelSpec
from kexp.control.opx.components import (Machine, Sticky, DigitalLine,
                                         AnalogDrive, IntegratedInput)
from kexp.control.opx.context import OPXShotContext
from kexp.control.opx.units import s_to_ns, hz_to_int

# What a K-machine sequence annotates ctx with: ctx.p.<name> completes
# against kexp's ExptParams.
KexpShotContext = OPXShotContext[ExptParams]

# --- ports (con1) ---
CON = 'con1'
RAMAN_80_ANALOG_PORT = 1       # OPX drive for the 80 MHz raman AO
RAMAN_150_ANALOG_PORT = 2      # OPX drive for the 150 MHz raman AO
RAMAN_SWITCH_DIGITAL_PORT = 1
IMAGING_SWITCH_DIGITAL_PORT = 2
HANDBACK_DIGITAL_PORT = 3
ACQUIRE_MARKER_DIGITAL_PORT = 4  # scope marker during the APD ADC window --
                                 # NOT the imaging switch line: the switch is
                                 # its own sticky element, and two elements
                                 # driving one digital port would fight
APD_ANALOG_IN_PORT = 1

# --- fixed hardware timing ---
T_APD_TIME_OF_FLIGHT_NS = 200   # digital marker -> ADC window start (a
                                # guess; QM's template used 28 ns. M3)
STICKY_ANALOG_RAMP_NS = 100     # ramp_to_zero duration for the sticky drives
T_DIGITAL_EDGE_NS = 16          # length of the block/pass level-set pulses
T_HANDBACK_TRIGGER_NS = 200
T_RAMAN_LATCH_NS = 1000         # sticky latch play; the tone holds after

# block = TTL high (ARTIQ RF blocked), pass = TTL low. See truth table.
BLOCK_LEVEL = 1

# --- element / operation names: the only names the QUA program text uses ---
RAMAN_80_ELEMENT = 'raman_80'
RAMAN_150_ELEMENT = 'raman_150'
RAMAN_SWITCH_ELEMENT = 'raman_switch'
IMAGING_SWITCH_ELEMENT = 'imaging_switch'
HANDBACK_ELEMENT = 'artiq_handback'
APD_ELEMENT = 'apd'
BLOCK_OP, PASS_OP = 'block', 'pass'
LATCH_OP = 'cw'
HANDBACK_OP = 'trigger'
ACQUIRE_OP = 'acquire'
INTEGRATION_WEIGHT = 'integration_window'
FULL_WEIGHT = 'full_pulse'

# The two-photon transition the Raman drives address, and which dds of
# expt.raman (the ARTIQ RamanBeamPair) each OPX analog element stands in for
# once the handoff TTL routes the AOs to the OPX.
RAMAN_TRANSITION_PARAM = 'frequency_raman_transition'
RAMAN_ELEMENT_DDS = {RAMAN_150_ELEMENT: 'raman_150_plus',
                     RAMAN_80_ELEMENT: 'raman_80_plus'}

# ExptParams keys compiled into the config / channel map once per run
# (design D2). Scanning or live-adjusting one would bake one shot's value
# into every shot while ARTIQ scans it, with no record -- so they are
# refused as xvars (manager) and as adjust() keys (tables.accessed), and a
# varying column raises in build_machine. frequency_raman_transition is
# NOT in this list: it is compiled at the first executed shot's value but
# the builder re-points the drives per shot when it is scanned (it is
# still recorded as accessed, so it cannot be live-adjusted).
CONFIG_TIME_PARAMS = (
    't_imaging_pulse_apd_abs',      # APD acquire pulse length
    't_opx_integration_start',      # integration window start
    't_opx_integration_len',        # integration window length (volts scale)
    't_opx_handoff_artiq_side',     # handoff: ARTIQ RF on after the trigger
    't_opx_handoff_opx_side',       # handoff: OPX body may start after the sum
    't_opx_handback_overlap',       # hand-back: blocks held after the edge
)


def config_time_params(expt=None, tables=None) -> tuple:
    """The config-time ExptParams keys (CONFIG_TIME_PARAMS), as the tuple
    ChannelMap.config_time_params carries. With ``tables`` (the per-shot
    ShotTables), every key is also recorded in tables.accessed -- so
    check_live_adjust_conflicts refuses adjust() on them -- and a key that
    varies per shot (scanned, or derived from a scanned parameter) raises:
    the config is compiled once, at one value, and would not follow the
    scan."""
    keys = tuple(CONFIG_TIME_PARAMS)
    if tables is not None:
        for key in keys:
            tables.accessed.add(key)
            if tables.has(key) and not tables.is_constant(key):
                col = tables.column(key)
                raise RuntimeError(
                    f"[opx] {key!r} is a config-time parameter (compiled "
                    f"into the OPX config once per run) but it varies per "
                    f"shot ({np.min(col):g} .. {np.max(col):g}): it is "
                    f"scanned as an xvar, or derived from one. The OPX "
                    f"cannot follow it -- fix it for the run, or give it a "
                    f"shot-time route through a ctx macro.")
    return keys


def raman_transition_to_ifs(expt):
    """-> f(transition Hz array) -> {element: IF Hz array}.

    The split is expt.raman.ao_frequencies: the same
    state_splitting_to_ao_frequency RamanBeamPair.set runs in the kernel, so
    the OPX drives the AOs at exactly the frequencies prep_raman() would
    have set on the DDSs for that transition.
    """
    pair = expt.raman
    which = {}
    for el, dds_name in RAMAN_ELEMENT_DDS.items():
        dds = getattr(expt.dds, dds_name)
        if dds is pair.dds0:
            which[el] = 0
        elif dds is pair.dds1:
            which[el] = 1
        else:
            raise RuntimeError(
                f"[opx] OPX element {el!r} stands in for dds.{dds_name}, but "
                f"that dds is not part of expt.raman -- the Raman split "
                f"cannot be mapped onto the OPX drives. Fix RAMAN_ELEMENT_DDS "
                f"or the RamanBeamPair wiring in kexp/base/devices.py.")

    def to_ifs(frequency_transition):
        f01 = pair.ao_frequencies(frequency_transition)
        return {el: f01[i] for el, i in which.items()}
    return to_ifs


def raman_config_transition(expt, tables=None) -> float:
    """The transition frequency the Raman drive IFs are compiled at: the
    first executed shot's value of frequency_raman_transition (from the
    per-shot tables when given, so a scanned or derived value is read in
    execution order). The builder re-points the IFs every shot when the
    value varies (see builder.py)."""
    key = RAMAN_TRANSITION_PARAM
    if tables is not None and tables.has(key):
        tables.accessed.add(key)
        return float(tables.column(key)[0])
    f = np.asarray(getattr(expt.params, key), dtype=float)
    if f.size != 1:
        raise ValueError(
            f"[opx] {key} has {f.size} values and no per-shot tables were "
            f"given to pick the first executed shot's.")
    return float(f.reshape(()))


def build_machine(expt, tables=None) -> Machine:
    """The K-machine OPX as components, from ExptParams + dds defaults.

    Raman drive IFs are the AO frequencies of expt.raman at the run's
    frequency_raman_transition (raman_config_transition), split by the same
    code as prep_raman() on the ARTIQ side. Amplitudes come from the dds
    frame defaults (kexp.config.dds_id: raman_80_plus / raman_150_plus) --
    used directly as waveform sample voltages, per the switch-box
    calibration. The APD acquire pulse is t_imaging_pulse_apd_abs long with
    the integration window from t_opx_integration_start/len.

    Validated before it is returned (amplitude limit, window fit, duplicate
    names, port clashes), so a bad value fails at opx.use() in prepare().
    """
    p = expt.params
    dds = expt.dds

    config_time_params(expt, tables)
    f_run = raman_config_transition(expt, tables)
    from_tables = tables is not None and tables.has(RAMAN_TRANSITION_PARAM)
    ifs = raman_transition_to_ifs(expt)(np.array([f_run]))

    acquire_ns = s_to_ns(p.t_imaging_pulse_apd_abs, key='t_imaging_pulse_apd_abs')
    w_start_ns = s_to_ns(p.t_opx_integration_start, key='t_opx_integration_start')
    w_len_ns = s_to_ns(p.t_opx_integration_len, key='t_opx_integration_len')

    def switch(name, port):
        return DigitalLine(
            name=name, con=CON, port=port,
            levels={BLOCK_OP: BLOCK_LEVEL, PASS_OP: 1 - BLOCK_LEVEL},
            edge_ns=T_DIGITAL_EDGE_NS,
            # sticky digital: 'block'/'pass' set the level, the element
            # holds it. analog=True is required by the QOP even here.
            sticky=Sticky(duration_ns=T_DIGITAL_EDGE_NS, analog=True,
                          digital=True))

    def drive(name, port):
        return AnalogDrive(
            name=name, con=CON, port=port,
            if_hz=hz_to_int(ifs[name][0]),
            amplitude_v=float(getattr(dds, RAMAN_ELEMENT_DDS[name]).amplitude),
            latch_ns=T_RAMAN_LATCH_NS, op=LATCH_OP,
            # sticky analog: the intensity servo needs the AO drives never
            # to drop, so these latch once per run and hold their tone
            sticky=Sticky(duration_ns=STICKY_ANALOG_RAMP_NS, analog=True,
                          digital=False))

    machine = Machine(
        con=CON,
        elements=[
            drive(RAMAN_80_ELEMENT, RAMAN_80_ANALOG_PORT),
            drive(RAMAN_150_ELEMENT, RAMAN_150_ANALOG_PORT),
            switch(RAMAN_SWITCH_ELEMENT, RAMAN_SWITCH_DIGITAL_PORT),
            switch(IMAGING_SWITCH_ELEMENT, IMAGING_SWITCH_DIGITAL_PORT),
            # hand-back: a 200 ns flag, not sticky
            DigitalLine(name=HANDBACK_ELEMENT, con=CON,
                        port=HANDBACK_DIGITAL_PORT,
                        levels={HANDBACK_OP: 1},
                        edge_ns=T_HANDBACK_TRIGGER_NS),
            # APD integrated readout; its marker goes to a spare digital
            # port for the scope, exposure is done by imaging_switch
            IntegratedInput(name=APD_ELEMENT, con=CON,
                            in_port=APD_ANALOG_IN_PORT,
                            marker_port=ACQUIRE_MARKER_DIGITAL_PORT,
                            acquire_ns=int(acquire_ns),
                            window_start_ns=int(w_start_ns),
                            window_len_ns=int(w_len_ns),
                            time_of_flight_ns=T_APD_TIME_OF_FLIGHT_NS,
                            gain_db=0, acquire_op=ACQUIRE_OP,
                            weight=INTEGRATION_WEIGHT,
                            full_weight=FULL_WEIGHT),
        ],
        extra={
            # what the config was compiled from (provenance)
            'transition_param': RAMAN_TRANSITION_PARAM,
            'frequency_raman_transition_hz': f_run,
            'transition_source': ('shot tables (first executed shot)'
                                  if from_tables else 'params'),
            'element_dds': dict(RAMAN_ELEMENT_DDS),
            'config_time_params': list(CONFIG_TIME_PARAMS),
            't_imaging_pulse_apd_abs': float(p.t_imaging_pulse_apd_abs),
            't_opx_integration_start': float(p.t_opx_integration_start),
            't_opx_integration_len': float(p.t_opx_integration_len),
        })
    machine.validate()
    return machine


def build_opx_config(expt, tables=None) -> dict:
    """The QUA config dict, built at finish_prepare from the experiment:
    build_machine(expt, tables).generate_config()."""
    return build_machine(expt, tables).generate_config()


def kexp_channel_map(expt, tables=None) -> ChannelMap:
    """The role map ('raman', 'imaging') over the machine's elements, plus
    the handshake windows and the config-time parameter list.

    Pass the per-shot ``tables`` when they exist (on_finish_prepare) so the
    attached machine is compiled at the first *executed* shot's transition,
    exactly as the config the job runs; without tables (opx.use() in
    prepare) it is compiled at the declared parameter value.
    """
    p = expt.params
    machine = build_machine(expt, tables)
    apd = machine.element(APD_ELEMENT)

    # Handoff settle (design D1): the OPX body may start once ARTIQ has
    # turned its RF on (t_opx_handoff_artiq_side after the trigger) and
    # that RF has settled (t_opx_handoff_opx_side more) -- the builder
    # waits this SUM after its block plays; ARTIQ returns to its caller at
    # the same point. The block-before-RF ordering within artiq_side is an
    # unmeasured hardware assumption (M1; see expt_params.py).
    settle_s = float(p.t_opx_handoff_artiq_side) + float(p.t_opx_handoff_opx_side)
    overlap_s = float(p.t_opx_handback_overlap)
    machine.extra.update({
        't_opx_handoff_artiq_side': float(p.t_opx_handoff_artiq_side),
        't_opx_handoff_opx_side': float(p.t_opx_handoff_opx_side),
        't_handoff_settle_s': settle_s,
        't_opx_handback_overlap': overlap_s,
        'guarded_channels': ['raman', 'imaging'],
    })

    cmap = ChannelMap(
        channels={
            'raman': ChannelSpec(
                switch_element=RAMAN_SWITCH_ELEMENT,
                analog_elements=(RAMAN_80_ELEMENT, RAMAN_150_ELEMENT),
                analog_latch_op=LATCH_OP,
                block_op=BLOCK_OP, pass_op=PASS_OP,
                transition_param=RAMAN_TRANSITION_PARAM,
                transition_to_ifs=raman_transition_to_ifs(expt)),
            'imaging': ChannelSpec(
                switch_element=IMAGING_SWITCH_ELEMENT,
                measure_element=APD_ELEMENT,
                acquire_op=apd.acquire_op,
                integration_weight=apd.weight,
                block_op=BLOCK_OP, pass_op=PASS_OP,
                # the raw parameter values (not the ns-rounded machine
                # fields), so ctx.measure's default exposure and the volts
                # conversion use exactly what ExptParams says
                t_acquire_s=float(p.t_imaging_pulse_apd_abs),
                t_integration_s=float(p.t_opx_integration_len)),
        },
        sync_channel='raman',
        handback_element=HANDBACK_ELEMENT,
        handback_op=HANDBACK_OP,
        # handoff_to_quantum_machines turns BOTH raman and imaging RF on
        # steady-state, so both switches are blocked in every OPX window
        # whatever the sequence claims
        guarded_channels=('raman', 'imaging'),
        t_handoff_settle_s=settle_s,
        t_handback_overlap_s=overlap_s,
        config_time_params=config_time_params(expt),
        machine=machine,
    )
    _check_map_against_machine(cmap, machine)
    return cmap


def _check_map_against_machine(cmap, machine):
    """Every element and operation the map names must exist on the machine
    (QUAM's play(validate=True), done once here instead of at open_qm)."""
    def need(el_name, op=None):
        el = machine.element(el_name)          # KeyError if missing
        if op is not None and op not in el.labels:
            raise ValueError(
                f"[opx] channel map names operation {op!r} on element "
                f"{el_name!r}, which only plays {el.labels}.")
    need(cmap.handback_element, cmap.handback_op)
    for role, spec in cmap.channels.items():
        need(spec.switch_element, spec.block_op)
        need(spec.switch_element, spec.pass_op)
        for el in spec.analog_elements:
            need(el, spec.analog_latch_op)
        if spec.measure_element is not None:
            need(spec.measure_element, spec.acquire_op)
            apd = machine.element(spec.measure_element)
            if spec.integration_weight not in (apd.weight, apd.full_weight):
                raise ValueError(
                    f"[opx] channel {role!r} integrates with weight "
                    f"{spec.integration_weight!r}, which {apd.name!r} does "
                    f"not define ({apd.weight!r}, {apd.full_weight!r}).")


def make_opx_manager(expt):
    """The OPXManager Base wires in as self.opx (host-only, inert until
    use(); imports no qm here)."""
    from kexp.control.opx.manager import OPXManager
    return OPXManager(expt,
                      host=QM_OPX_IP,
                      cluster=QM_OPX_CLUSTER,
                      map_builder=kexp_channel_map,
                      config_builder=build_opx_config)
