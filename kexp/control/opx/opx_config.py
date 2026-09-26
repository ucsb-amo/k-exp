"""K-machine OPX+ wiring: QUA config from ExptParams + dds defaults, the
channel role map, and the manager factory Base uses.

This is the lab-specific half of kexp.control.opx (the dds_frame analog for
the OPX). Everything physical lives here: ports, element names, polarities,
and which ExptParams / dds defaults feed which config value.

Config-time vs shot-time: values in this file are compiled into the QUA
config ONCE per run (analog drive frequencies/amplitudes, acquire and
integration windows). They cannot be xvars -- a scan of one of these needs a
shot-time route (update_frequency / amp() via ctx) or is an error. Pulse
durations, detunings and phases are shot-time and scan freely. The Raman
drive IFs have that route built in: they follow frequency_raman_transition
(split by expt.raman, the ARTIQ RamanBeamPair), compiled at the first
shot's value and updated per shot by the builder when it is scanned.

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
from kexp.control.opx.context import OPXShotContext
from kexp.control.opx.units import s_to_ns, hz_to_int, MAX_ANALOG_V

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
T_APD_TIME_OF_FLIGHT_NS = 200   # digital marker -> ADC window start
STICKY_ANALOG_RAMP_NS = 100     # ramp_to_zero duration for the sticky drives
T_DIGITAL_EDGE_NS = 16          # length of the block/pass level-set pulses
T_HANDBACK_TRIGGER_NS = 200
T_RAMAN_LATCH_NS = 1000         # sticky latch play; the tone holds after

# block = TTL high (ARTIQ RF blocked), pass = TTL low. See truth table.
BLOCK_LEVEL = 1

# The two-photon transition the Raman drives address, and which dds of
# expt.raman (the ARTIQ RamanBeamPair) each OPX analog element stands in for
# once the handoff TTL routes the AOs to the OPX.
RAMAN_TRANSITION_PARAM = 'frequency_raman_transition'
RAMAN_ELEMENT_DDS = {'raman_150': 'raman_150_plus',
                     'raman_80': 'raman_80_plus'}


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


def kexp_channel_map(expt) -> ChannelMap:
    p = expt.params
    return ChannelMap(
        channels={
            'raman': ChannelSpec(
                switch_element='raman_switch',
                analog_elements=('raman_80', 'raman_150'),
                transition_param=RAMAN_TRANSITION_PARAM,
                transition_to_ifs=raman_transition_to_ifs(expt)),
            'imaging': ChannelSpec(
                switch_element='imaging_switch',
                measure_element='apd',
                t_acquire_s=float(p.t_imaging_pulse_apd_abs),
                t_integration_s=float(p.t_opx_integration_len)),
        },
        sync_channel='raman',
        handback_element='artiq_handback',
        # handoff_to_quantum_machines turns BOTH raman and imaging RF on
        # steady-state, so both switches are blocked in every OPX window
        # whatever the sequence claims
        guarded_channels=('raman', 'imaging'),
        # the handshake windows, shared with Control.handoff_to_quantum_machines
        t_handoff_settle_s=float(p.t_opx_handoff_settle),
        t_handback_overlap_s=float(p.t_opx_handback_overlap),
    )


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


def build_opx_config(expt, tables=None) -> dict:
    """The QUA config dict, built at finish_prepare from the experiment.

    Raman drive IFs are the AO frequencies of expt.raman at the run's
    frequency_raman_transition (raman_config_transition), split by the same
    code as prep_raman() on the ARTIQ side. Amplitudes come from the dds
    frame defaults (kexp.config.dds_id: raman_80_plus / raman_150_plus) --
    used directly as waveform sample voltages, per the switch-box
    calibration.
    """
    p = expt.params
    dds = expt.dds

    ifs = raman_transition_to_ifs(expt)(
        np.array([raman_config_transition(expt, tables)]))
    f_80 = hz_to_int(ifs['raman_80'][0])
    f_150 = hz_to_int(ifs['raman_150'][0])
    a_80 = float(dds.raman_80_plus.amplitude)
    a_150 = float(dds.raman_150_plus.amplitude)
    for name, a in (('raman_80', a_80), ('raman_150', a_150)):
        if abs(a) > MAX_ANALOG_V:
            raise ValueError(
                f"[opx] {name} drive amplitude {a} V exceeds the OPX analog "
                f"output limit of {MAX_ANALOG_V} V.")

    acquire_ns = s_to_ns(p.t_imaging_pulse_apd_abs, key='t_imaging_pulse_apd_abs')
    w_start_ns = s_to_ns(p.t_opx_integration_start, key='t_opx_integration_start')
    w_len_ns = s_to_ns(p.t_opx_integration_len, key='t_opx_integration_len')
    tail_ns = acquire_ns - w_start_ns - w_len_ns
    if tail_ns < 0:
        raise ValueError(
            f"[opx] integration window (start {w_start_ns} ns + len "
            f"{w_len_ns} ns) does not fit in the acquire window "
            f"({acquire_ns} ns = t_imaging_pulse_apd_abs).")
    window = [(0.0, int(w_start_ns)), (1.0, int(w_len_ns)),
              (0.0, int(tail_ns))]
    window = [(v, ns) for v, ns in window if ns > 0]

    def _digital_input(port, name='in'):
        return {name: {'port': (CON, port), 'delay': 0, 'buffer': 0}}

    return {
        'controllers': {
            CON: {
                'type': 'opx1',
                'analog_outputs': {
                    RAMAN_80_ANALOG_PORT: {'offset': 0.0},
                    RAMAN_150_ANALOG_PORT: {'offset': 0.0},
                },
                'digital_outputs': {
                    RAMAN_SWITCH_DIGITAL_PORT: {},
                    IMAGING_SWITCH_DIGITAL_PORT: {},
                    HANDBACK_DIGITAL_PORT: {},
                    ACQUIRE_MARKER_DIGITAL_PORT: {},
                },
                'analog_inputs': {
                    APD_ANALOG_IN_PORT: {'offset': 0.0, 'gain_db': 0},
                },
            },
        },
        'elements': {
            # sticky analog: the intensity servo needs the AO drives never
            # to drop, so these latch once per run and hold their tone
            'raman_80': {
                'singleInput': {'port': (CON, RAMAN_80_ANALOG_PORT)},
                'intermediate_frequency': f_80,
                'sticky': {'analog': True, 'duration': STICKY_ANALOG_RAMP_NS},
                'operations': {'cw': 'raman_80_cw'},
            },
            'raman_150': {
                'singleInput': {'port': (CON, RAMAN_150_ANALOG_PORT)},
                'intermediate_frequency': f_150,
                'sticky': {'analog': True, 'duration': STICKY_ANALOG_RAMP_NS},
                'operations': {'cw': 'raman_150_cw'},
            },
            # sticky digital switches: 'block'/'pass' set the level, the
            # element holds it (see the crash-state note in builder.py: the
            # job is halted when the ARTIQ process exits, and the lines then
            # idle low = pass). The QOP requires 'analog': True even on a
            # digital-only element ("sticky digital but analog sticky wasn't
            # set" job failure otherwise); it is a no-op with no analog
            # waveforms.
            'raman_switch': {
                'digitalInputs': _digital_input(RAMAN_SWITCH_DIGITAL_PORT),
                'sticky': {'analog': True, 'digital': True,
                           'duration': T_DIGITAL_EDGE_NS},
                'operations': {'block': 'block_pulse', 'pass': 'pass_pulse'},
            },
            'imaging_switch': {
                'digitalInputs': _digital_input(IMAGING_SWITCH_DIGITAL_PORT),
                'sticky': {'analog': True, 'digital': True,
                           'duration': T_DIGITAL_EDGE_NS},
                'operations': {'block': 'block_pulse', 'pass': 'pass_pulse'},
            },
            'artiq_handback': {
                'digitalInputs': _digital_input(HANDBACK_DIGITAL_PORT),
                'operations': {'trigger': 'handback_trigger_pulse'},
            },
            # APD integrated readout; its marker goes to a spare digital
            # port for the scope, exposure is done by imaging_switch
            'apd': {
                'digitalInputs': _digital_input(ACQUIRE_MARKER_DIGITAL_PORT),
                'outputs': {'out1': (CON, APD_ANALOG_IN_PORT)},
                'time_of_flight': T_APD_TIME_OF_FLIGHT_NS,
                'smearing': 0,
                'operations': {'acquire': 'apd_acquire'},
            },
        },
        'pulses': {
            'raman_80_cw': {
                'operation': 'control',
                'length': T_RAMAN_LATCH_NS,
                'waveforms': {'single': 'raman_80_wf'},
            },
            'raman_150_cw': {
                'operation': 'control',
                'length': T_RAMAN_LATCH_NS,
                'waveforms': {'single': 'raman_150_wf'},
            },
            'block_pulse': {
                'operation': 'control',
                'length': T_DIGITAL_EDGE_NS,
                'digital_marker': 'block_wf',
            },
            'pass_pulse': {
                'operation': 'control',
                'length': T_DIGITAL_EDGE_NS,
                'digital_marker': 'pass_wf',
            },
            'handback_trigger_pulse': {
                'operation': 'control',
                'length': T_HANDBACK_TRIGGER_NS,
                'digital_marker': 'trigger_wf',
            },
            'apd_acquire': {
                'operation': 'measurement',
                'length': int(acquire_ns),
                'digital_marker': 'trigger_wf',
                'integration_weights': {
                    'integration_window': 'integration_window',
                    'full_pulse': 'full_pulse',
                },
            },
        },
        'waveforms': {
            'raman_80_wf': {'type': 'constant', 'sample': a_80},
            'raman_150_wf': {'type': 'constant', 'sample': a_150},
        },
        'digital_waveforms': {
            'block_wf': {'samples': [(BLOCK_LEVEL, 0)]},
            'pass_wf': {'samples': [(1 - BLOCK_LEVEL, 0)]},
            'trigger_wf': {'samples': [(1, 0)]},
        },
        'integration_weights': {
            'integration_window': {
                'cosine': window,
                'sine': [(0.0, ns) for _v, ns in window],
            },
            'full_pulse': {
                'cosine': [(1.0, int(acquire_ns))],
                'sine': [(0.0, int(acquire_ns))],
            },
        },
    }


def make_opx_manager(expt):
    """The OPXManager Base wires in as self.opx (host-only, inert until
    use(); imports no qm here)."""
    from kexp.control.opx.manager import OPXManager
    return OPXManager(expt,
                      host=QM_OPX_IP,
                      cluster=QM_OPX_CLUSTER,
                      map_builder=kexp_channel_map,
                      config_builder=build_opx_config)
