"""Host-side connections the K-machine monitor server holds between runs.

Shown on the Composite tab's connection bar (one pill each).  The server opens
them when the monitor is running, releases them before it replies to a run's
announcement (the run opens the AWG itself in ``init_kernel``), and runs each
in its own agent process -- see ``waxx.util.device_state.connections`` and
``waxx.util.device_state.connection_agent``.

Light on purpose: the server, the Device Control GUI and
``kexp.config.composite_devices`` all import this; the driver itself is only
imported inside the agent process.
"""

from waxx.util.device_state.connections import Connection

from kexp.config.ip import AWG_IP

#: ctx.connection(AWG_CONNECTION_KEY) in the composite definitions.
AWG_CONNECTION_KEY = "tweezer_awg"

#: How long the server's open waits while another connection holds the card
#: (a run waits 30 s).  It runs on the server's own thread, not the monitor
#: loop, so it can be longer than the monitor could afford.
T_AWG_OPEN_WAIT_IN_USE = 10.

AWG_CONNECTION = Connection(
    key=AWG_CONNECTION_KEY,
    label="Tweezer AWG",
    driver="waxx.control.tweezer.awg_agent_driver:TweezerAwgDriver",
    driver_kwargs={"awg_ip": AWG_IP, "t_wait_in_use": T_AWG_OPEN_WAIT_IN_USE},
    tooltip="Spectrum AWG netbox (one connection at a time), held by the monitor server "
            "between runs. Opened when the monitor is running, with no tones ('Apply "
            "traps' on the Tweezer card loads them); released before a run starts (the "
            "run opens it itself).",
    confirm="The AWG card is stopped: the tweezer AOD gets no RF from it until it is "
            "connected again and traps are applied.",
    open_timeout_s=T_AWG_OPEN_WAIT_IN_USE + 20.,
)

MONITOR_CONNECTIONS = (AWG_CONNECTION,)
