"""The K machine's Andor camera server: beacon's (``beacon.andor``) with the
serial, the readout settings and the lab's constraints from kexp's config.

    python -m kexp.control.cameras.andor_server [--port N] [--serial S]

Serves ``camera_server:<host>:andor`` with the camera ``andor_emccd:<serial>``
(``cameras.andor.serial_no``) -- the id liveOD's camera host gives the
Andor, so liveOD borrows it from this server when it needs it (its start,
its live view, a run's INIT_RUN), as it borrows a Basler from the beacon
server.  The camera is opened only when a client opens it (a Camera Viewer
attaching) and closed after the last one leaves; an idle server holds nothing.
Only one process can hold the Andor: while liveOD or the SLM spot finder has
it, an open here fails naming the holder.

Applied on every apply, live and run: the category's rules, the lab's
constraints (``kexp.config.live_od.andor_constraints``: the DU897's 0.3 us /
Normal vertical clock is refused).  The live profile starts from
``cameras.andor``'s readout settings (hs_speed, vs_speed, vs_amp, preamp,
baseline_clamp); a saved default goes on top.
"""
from __future__ import annotations

import sys

from beacon.drivers.andor.provider import AndorProvider

READOUT_KEYS = ("hs_speed", "vs_speed", "vs_amp", "preamp", "baseline_clamp")


class KexpAndorProvider(AndorProvider):
    """``AndorProvider`` with kexp's camera table and constraints as defaults
    (a ``--serial`` given on the command line wins)."""

    @classmethod
    def from_args(cls, args) -> "KexpAndorProvider":
        from kexp.config.camera_id import cameras
        from kexp.config.live_od import andor_constraints
        andor = cameras.andor
        serials = args.serial or [andor.serial_no]
        readout = {k: getattr(andor, k) for k in READOUT_KEYS if hasattr(andor, k)}
        return cls(serials, constraints=andor_constraints(), readout=readout,
                   live_em_gain_cap=args.live_em_gain_cap)


def main(argv=None) -> int:
    from beacon.camera.server import main as serve
    return serve(argv, provider="kexp.control.cameras.andor_server:KexpAndorProvider")


if __name__ == "__main__":
    sys.exit(main())
