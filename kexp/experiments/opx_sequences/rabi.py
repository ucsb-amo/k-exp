"""Raman Rabi sequences.

A sequence is one shot's OPX-side body, between the ARTIQ trigger and the
hand-back (both owned by the builder -- see kexp.control.opx.builder). All
times are SI seconds; ctx.p.<param> tracks the scan per shot exactly like
self.p in a scan_kernel, and arithmetic on it (ctx.p.t_raman_pi_pulse / 2)
is worked out per shot on the host before the program is built.

The Raman analog drives (raman_80 / raman_150, sticky) are latched once per
run by the builder so the intensity servo never sees the RF drop; a "pulse"
here is the common switch AOM gate opening for the requested time. They
latch at amp(sqrt(fraction_power_raman)) of the dds_id amplitudes -- what
prep_raman() sets on the ARTIQ DDSs -- so set self.p.fraction_power_raman in
prepare() to change the Raman power (one value per run: not an xvar).

That switch AOM is NOT kept warm by the sticky drives -- its thermal
warm-up (and the raman shutter) stay ARTIQ's job: call prep_raman() before
handoff_to_quantum_machines(), which pulses the switch AOM 3 ms with the
shutter still closed and only then opens the shutter.
"""

from kexp.control.opx import opx_sequence, KexpShotContext


@opx_sequence('rabi_raman_pulse', claims=('raman',))
def rabi_raman_pulse(ctx: KexpShotContext):
    """One Raman exposure of t_raman_pulse. Readout is ARTIQ's (camera
    absorption image after the hand-back) -- no OPX data. The OPX analog of
    experiments/qm/qm_rabi_frequency.py's manual companion program."""
    ctx.raman_pulse(ctx.p.t_raman_pulse)


@opx_sequence('rabi_raman_apd', claims=('raman', 'imaging'),
              measurements={'apd_qm': 4})
def rabi_raman_apd(ctx: KexpShotContext):
    """Rabi pulse + 4-point integrated APD readout: the OPX analog of
    Control.tof_apd_abs_image's pulse train. ARTIQ side: release the trap
    and take the TOF delay before handoff_to_quantum_machines().

    apd_qm per shot: [with-atoms |a>, with-atoms after pi-pulse |b>,
    light (atoms gone), dark (beam blocked)]. Values are mean volts over
    the integration window (t_opx_integration_len).
    """
    ctx.raman_pulse(ctx.p.t_raman_pulse)
    ctx.wait_s(3.e-6)
    ctx.measure('apd_qm')                    # atoms, |a>
    ctx.wait_s(3.e-6)
    ctx.raman_pulse(ctx.p.t_raman_pi_pulse)
    ctx.wait_s(2.e-6)
    ctx.measure('apd_qm')                    # atoms, |b>
    ctx.wait_s(200.e-6)
    ctx.measure('apd_qm')                    # light, atoms blown away
    ctx.wait_s(10.e-6)
    ctx.measure('apd_qm', expose=False)      # dark
