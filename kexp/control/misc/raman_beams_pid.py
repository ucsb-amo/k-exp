"""The Raman beam pair under the Raman intensity stabilization PID, with the PID's hold.

``RamanBeamsPID`` is the waxx ``RamanBeamsPID`` (powers set by the PID setpoint
DACs, DDS amplitudes at their defaults) plus the client of the Raman intensity
PID server (``kexp.util.guis.lasers.raman_intensity``), so a sequence can fix
the PID outputs (``hold``) and free them again (``release``).
"""

from artiq.experiment import kernel, rpc, TBool
from artiq.language.core import now_mu, delay

from waxx.control.artiq import DDS, DAC_CH, DummyCore
from waxx.control.raman_beams import RamanBeamsPID as RamanBeamsPIDWaxx, dv
from kexp.config.expt_params import ExptParams

#: Wait between writing the setpoints and asking for the hold, so the PID has settled.
T_PID_SETTLE_BEFORE_HOLD = 5.e-3


class RamanBeamsPID(RamanBeamsPIDWaxx):
    """See waxx.control.raman_beams.RamanBeamsPID for how fraction_power maps to
    the setpoints. Adds hold() / release() of the Raman intensity PID.

    The server is found on the first hold or release (up to a few seconds);
    call connect() in prepare() to do that ahead of the run.

    A hold or release that fails is printed with a ``!!`` banner and counted in
    ``n_pid_requests_failed``; it never raises (an exception in an async RPC
    would stop the host while the kernel is still running, with no cleanup).
    """

    def __init__(self,
                 dds0:DDS,
                 dds1:DDS,
                 dds_sw:DDS,
                 dac_pid0:DAC_CH,
                 dac_pid1:DAC_CH,
                 core=DummyCore(),
                 params=ExptParams(),
                 frequency_transition=0.,
                 fraction_power=0.):
        self.core = core
        self._pid_client = None
        self.n_pid_requests_failed = 0
        super().__init__(dds0=dds0,
                         dds1=dds1,
                         dds_sw=dds_sw,
                         dac_pid0=dac_pid0,
                         dac_pid1=dac_pid1,
                         params=params,
                         frequency_transition=frequency_transition,
                         fraction_power=fraction_power)

    def connect(self, discovery_timeout=3.0):
        """Host-side: find the Raman intensity PID server now. Raises if it is not found."""
        from kexp.util.guis.lasers.raman_intensity import client  # noqa: PLC0415
        self._pid_client = client(discovery_timeout=discovery_timeout)
        return self._pid_client

    @kernel
    def hold(self, fraction_power_raman=dv):
        """Sets the PID setpoints for fraction_power_raman (default: the param
        fraction_power_raman), waits 5 ms, then asks the PID server to hold
        both PID outputs at their values.

        The hold is an RPC, so it should be done well ahead of when it is
        needed. The call waits until the RTIO counter reaches the timeline
        cursor (core.wait_until_mu(now_mu())) after the 5 ms, then sends the
        request without waiting for a reply (async): the PID is held some
        milliseconds to tens of milliseconds later (host, network and serial
        round trips), and the kernel does not learn whether it worked (a
        failure is printed on the host). The call returns with no slack, so
        add a delay before the next RTIO event. The hold stays on, across
        shots and runs, until release().
        """
        if fraction_power_raman < 0.:
            fraction_power_raman = self.p.fraction_power_raman
        self.set_power(fraction_power_raman)
        delay(T_PID_SETTLE_BEFORE_HOLD)
        self.core.wait_until_mu(now_mu())
        self._request_pid_hold(True)

    @kernel
    def release(self):
        """Asks the PID server to release the hold (bumpless). An RPC, like
        hold(): sent at the timeline cursor (core.wait_until_mu(now_mu())),
        takes effect milliseconds later, and returns with no slack."""
        self.core.wait_until_mu(now_mu())
        self._request_pid_hold(False)

    @rpc(flags={"async"})
    def _request_pid_hold(self, on: TBool):
        what = "hold" if on else "release"
        try:
            from waxx.util.guis.intensity_pid.intensity_pid_client import (  # noqa: PLC0415
                IntensityPIDError, require_ok)
            if self._pid_client is None:
                self.connect()
            reply = require_ok(self._pid_client.hold(bool(on)))
            if reply.get("on") is not None and bool(reply["on"]) != bool(on):
                raise IntensityPIDError(f"the server reports hold = {reply['on']}")
        except Exception as e:
            self.n_pid_requests_failed += 1
            print(f"!! [raman intensity PID] {what} request FAILED "
                  f"({self.n_pid_requests_failed} failed this run): {e!r}\n"
                  f"!!   The PID was not {'held' if on else 'released'} as the sequence asked; "
                  f"shots from here on ran with it in an unknown state.")
