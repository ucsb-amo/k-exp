"""Role map between lab beam channels and OPX config element names.

The generic builder/context speak in *roles* ('raman', 'imaging'); which QUA
elements those correspond to -- and which digital line blocks the ARTIQ RF
for each -- is lab wiring, defined once in kexp.control.opx.opx_config (the
dds_frame analog for the OPX).

Switch polarity (K machine, 2026-09): the OPX digital TTL drives an RF
switch in the ARTIQ RF path of each beam's switch AOM. TTL low = ARTIQ RF
passes (the idle/off-job state, so ARTIQ gates its own light when the OPX is
not involved); TTL high = RF blocked. Ops on a switch element are therefore
'block' (drive 1, sticky-held) and 'pass' (drive 0, sticky-held) -- exposing
the atoms during an OPX window means playing 'pass' for the pulse duration
and immediately re-playing 'block'.

Generic (future waxx.control.opx): no kexp imports, no qm imports.
"""

from dataclasses import dataclass, field


@dataclass
class ChannelSpec:
    """One beam channel the OPX can guard/drive.

    switch_element: digital-only, sticky element on the RF-block line.
    analog_elements: sticky analog elements latched once per run (e.g. the
        two Raman AO drives, which the intensity servo needs never to drop).
    measure_element: element with an ADC input for this channel's detector
        (the APD behind the imaging path), or None.
    """
    switch_element: str
    analog_elements: tuple = ()
    analog_latch_op: str = 'cw'
    measure_element: str = None
    acquire_op: str = 'acquire'
    integration_weight: str = 'integration_window'
    block_op: str = 'block'
    pass_op: str = 'pass'
    # measurement timing (SI seconds; filled from ExptParams by the lab's
    # map builder): the acquire/exposure window length, and the integration
    # window length used to convert raw integration results to mean volts
    t_acquire_s: float = None
    t_integration_s: float = None


@dataclass
class ChannelMap:
    """The full role map plus the handshake elements.

    sync_channel: role whose switch element executes wait_for_trigger (all
        other elements are align()ed to it each shot).
    handback_element / handback_op: the digital pulse that hands control
        back to ARTIQ (ttl.quantum_machines_receive_trigger on the other
        end).
    guarded_channels: roles whose ARTIQ RF the handoff kernel turns on
        steady-state -- the builder blocks these during *every* OPX window
        regardless of what the sequence claims, because light would leak
        otherwise (kexp handoff_to_quantum_machines turns on both raman and
        imaging RF unconditionally).
    t_handoff_settle_s / t_handback_overlap_s: the two handshake windows
        (SI seconds). The body waits t_handoff_settle_s after the trigger
        before anything exposes (ARTIQ's RF comes on halfway through it);
        the blocks stay high t_handback_overlap_s after the hand-back
        trigger (ARTIQ's RF goes off halfway through it). The lab's map
        builder fills both from ExptParams so both sides of the handshake
        read the same numbers; there are no defaults on purpose.
    """
    channels: dict = field(default_factory=dict)
    sync_channel: str = ''
    handback_element: str = ''
    handback_op: str = 'trigger'
    guarded_channels: tuple = ()
    t_handoff_settle_s: float = None
    t_handback_overlap_s: float = None

    def __post_init__(self):
        for name in ('t_handoff_settle_s', 't_handback_overlap_s'):
            v = getattr(self, name)
            if v is None or not v > 0.:
                raise ValueError(
                    f"[opx] ChannelMap.{name} must be a positive time in "
                    f"seconds (got {v!r}); the map builder fills it from "
                    f"ExptParams.")

    def spec(self, role) -> ChannelSpec:
        try:
            return self.channels[role]
        except KeyError:
            raise KeyError(
                f"[opx] unknown channel role {role!r}; "
                f"defined roles: {sorted(self.channels)}")
