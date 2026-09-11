"""Experiment-side control of the APD pickoff stage (Thorlabs PDXC).

The stage carries a beamsplitter: when it is IN the beamsplitter feeds the
APD and blocks the Andor camera, when it is OUT the camera is clear.  The two
are mutually exclusive.

``APDStageClient`` wraps ``waxx.control.misc.pdxc.PDXC_Client`` so experiments
get one named object with explicit methods rather than raw RPC calls, and so a
missing PDXC server degrades to warnings instead of stopping a run.
"""

from waxx.control.misc.pdxc import (
    PDXC_Client,
    POSITION_IN,
    POSITION_OUT,
    POSITION_UNKNOWN,
)


class APDStageClient():
    """The beamsplitter stage that picks light off to the APD.

    Every method degrades to a no-op with a printed warning when the PDXC
    server is unreachable, so a missing stage server never stops a run.

    Reachability is decided once, at construction: an experiment that starts
    while the server is down stays in warn-and-skip mode for its lifetime
    rather than having the stage come alive partway through a run.

    A call that fails *after* a successful connection (server gone, stage
    fault) raises by default.  With ``raise_on_error=False`` it prints a
    warning and returns None instead -- Clients passes that for
    ``suppress_live_od=True`` runs.
    """

    def __init__(self, discovery_timeout=3.0, raise_on_error=True):
        self._raise_on_error = raise_on_error
        try:
            self._client = PDXC_Client(discovery_timeout=discovery_timeout)
        except Exception as e:
            print(f"[PDXC] WARNING: no connection to the PDXC stage server: {e}\n"
                  "       APD stage control is disabled for this run. Start the "
                  "PDXC server on the control PC if you need it.")
            self._client = None

    @property
    def connected(self):
        """True when the PDXC server was reachable at startup."""
        return self._client is not None

    def _warn(self, what):
        print(f"[PDXC] WARNING: not connected -- skipping {what}.")
        return None

    def _call(self, what, method, *args, **kwargs):
        """Run ``self._client.<method>``, or warn and skip when not connected.

        Communication errors raise unless ``raise_on_error=False``, in which
        case they print a warning and return None.
        """
        if not self.connected:
            return self._warn(what)
        try:
            return getattr(self._client, method)(*args, **kwargs)
        except Exception as e:
            if self._raise_on_error:
                raise
            print(f"[PDXC] WARNING: {what} failed: {e}\n"
                  "       Continuing without APD stage control.")
            return None

    # ------------------------------------------------------------------
    # Position
    # ------------------------------------------------------------------

    def set_apd_stage(self, apd_stage=None):
        """Position the stage for this experiment.

        * ``apd_stage=True``  -> stage in:  light to the APD, camera blocked.
        * ``apd_stage=False`` -> stage out: camera clear.
        * ``apd_stage=None``  -> do nothing; the stage stays where it is.

        This method infers nothing.  Base.__init__ resolves the position from
        ``camera_select`` and ``setup_camera``
        (kexp.base.cameras.resolve_run_config): acquiring with cameras.apd
        asks for in, grabbing frames with a real camera asks for out, and
        acquiring nothing passes None.  ``override_apd_stage`` forces it.

        The server remembers the last commanded position, so a run that
        already has the stage where it needs it returns immediately without
        moving.  Only the first run after a change pays the throw.
        """
        if apd_stage is None:
            return None
        return self.move_to(POSITION_IN if apd_stage else POSITION_OUT)

    def move_to(self, state, force=False):
        """Drive the stage to ``POSITION_IN`` or ``POSITION_OUT``."""
        result = self._call(f"move to {state}", "move_to", state, force=force)
        if result is not None:
            print(f"[PDXC] APD stage {result}.")
        return result

    def apd_in(self, force=False):
        """Insert the beamsplitter: light to the APD, camera blocked."""
        return self.move_to(POSITION_IN, force=force)

    def apd_out(self, force=False):
        """Retract the beamsplitter: camera clear."""
        return self.move_to(POSITION_OUT, force=force)

    def position(self):
        """Last commanded position: 'in', 'out' or 'unknown'."""
        if not self.connected:
            return POSITION_UNKNOWN
        result = self._call("position query", "get_position_state")
        return POSITION_UNKNOWN if result is None else result

    def declare_position(self, state):
        """Tell the server where the stage is without moving it.

        For recovering the tracked position after the stage was moved by hand.
        """
        return self._call(f"declaring position {state}",
                          "set_position_state", state)

    # ------------------------------------------------------------------
    # Jogs (relative moves; these leave the tracked position unknown)
    # ------------------------------------------------------------------

    def jog_in(self, steps=None):
        """Jog toward the APD by *steps* pulses (default: server step size)."""
        return self._call("jog in", "move_in", steps=steps)

    def jog_out(self, steps=None):
        """Jog toward the camera by *steps* pulses (default: server step size)."""
        return self._call("jog out", "move_out", steps=steps)

    # ------------------------------------------------------------------
    # Settings (persisted on the server)
    # ------------------------------------------------------------------

    def get_step_size(self):
        """Pulses used by jog_in / jog_out when no count is given."""
        return self._call("step size query", "get_step_size")

    def set_step_size(self, steps):
        """Set the default jog size, in pulses."""
        return self._call("step size set", "set_step_size", steps)

    def get_throw_pulses(self):
        """Pulses per move issued by a full throw."""
        return self._call("throw pulses query", "get_throw_pulses")

    def set_throw_pulses(self, pulses):
        """Set the pulses per move used by a full throw."""
        return self._call("throw pulses set", "set_throw_pulses", pulses)

    def get_throw_moves(self, state):
        """Number of moves a full throw to *state* issues."""
        return self._call(f"throw moves query for {state}",
                          "get_throw_moves", state)

    def set_throw_moves(self, state, moves):
        """Set the number of moves a full throw to *state* issues."""
        return self._call(f"throw moves set for {state}",
                          "set_throw_moves", state, moves)
