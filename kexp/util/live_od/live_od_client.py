"""
ZMQ REQ client used by the experiment process to communicate with LiveODServer.

All public methods are synchronous (blocking) and must be called sequentially
— one outstanding request at a time, matching the REQ/REP pattern.

Typical per-run sequence:

    reply = client.init_run(payload)          # INIT_RUN
    if capture_images:
        client.wait_cam_ready()               # WAIT_CAM_READY
    for each shot:
        client.shot_complete(idx, N, xvars)   # SHOT_COMPLETE
    client.end_run(payload)                   # END_RUN
"""

import pickle
import time

import zmq

from beacon.discovery.client import NetClient
from waxx.util.comms_server.hardware_id import resolve_scoped_server_id


# wait_cam_ready asks in slices this long, so a reset is noticed within one slice.
CAM_READY_SLICE_S = 0.5


class LiveODClient(NetClient):
    """REQ socket client for LiveODServer."""

    def __init__(self, timeout_ms: int = 5000, discovery_timeout: float = 10.0):
        super().__init__(resolve_scoped_server_id("live_od"), discovery_timeout=discovery_timeout)
        self._ip = self.host
        self._port = self.port
        self._timeout_ms = timeout_ms
        # Context and socket are created lazily on first _send_recv call so
        # that constructing this object in Base.__init__ / prepare() does NOT
        # open a network connection immediately.
        self._context = None
        self._socket = None
        self.last_adjust_values: dict = {}
        # Reset flag from the latest server reply that carried one.
        self.last_reset_requested: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self):
        """(Re)create the REQ socket and connect to the server."""
        if self._context is None:
            self._context = zmq.Context()
        if self._socket is not None:
            try:
                self._socket.setsockopt(zmq.LINGER, 0)
                self._socket.close()
            except Exception:
                pass
        self._socket = self._context.socket(zmq.REQ)
        self._socket.setsockopt(zmq.SNDTIMEO, self._timeout_ms)
        self._socket.setsockopt(zmq.RCVTIMEO, self._timeout_ms)
        self._socket.connect(f"tcp://{self._ip}:{self._port}")

    def _rediscover(self) -> None:
        """Update ``_ip``/``_port`` from the latest beacon cache.

        Delegates to ``NetClient._rediscover()`` then syncs the ZMQ
        address fields from the updated ``self.host``/``self.port``.
        """
        super()._rediscover(timeout=2.0)
        self._ip = self.host
        self._port = self.port

    def _send_recv(self, payload: dict, rcvtimeo_ms: int = None) -> dict:
        """Send ``payload`` and return the decoded reply.

        If ``rcvtimeo_ms`` is given, the receive timeout is temporarily
        overridden (e.g. for WAIT_CAM_READY and END_RUN which can be slow).
        """
        if self._socket is None:
            self._connect()
        if rcvtimeo_ms is not None:
            self._socket.setsockopt(zmq.RCVTIMEO, rcvtimeo_ms)
        try:
            self._socket.send(pickle.dumps(payload))
            return pickle.loads(self._socket.recv())
        except zmq.Again:
            # Re-discover in case liveOD restarted on a new port, then
            # recreate the socket to the (possibly updated) address.
            self._rediscover()
            self._connect()
            raise ConnectionError(
                f"[LiveODClient] No response from liveOD server at "
                f"tcp://{self._ip}:{self._port}. Is liveOD running?"
            )
        finally:
            if rcvtimeo_ms is not None:
                self._socket.setsockopt(zmq.RCVTIMEO, self._timeout_ms)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def init_run(self, payload: dict) -> dict:
        """Send INIT_RUN.  Returns ``{"run_id": int, "filepath": str}``.

        The server creates and fully populates the HDF5 data file before
        replying, so this can take a while on a slow/mapped data drive — hence
        the raised receive timeout rather than the 5 s default.
        """
        payload["tag"] = "INIT_RUN"
        self.last_reset_requested = False    # the server clears its flag on INIT_RUN
        reply = self._send_recv(payload, rcvtimeo_ms=60_000)
        if not reply.get("ok"):
            raise RuntimeError(
                f"[LiveODClient] INIT_RUN failed: {reply.get('error')}"
            )
        return reply

    def wait_cam_ready(self, timeout: float = 60.0) -> bool:
        """Block until liveOD confirms the camera is ready.

        Returns True when the camera is ready and False when a reset was
        requested while waiting (``last_reset_requested`` is then set) -- the
        caller aborts the run. Raises ValueError on timeout or failure.

        The wait is asked for in slices of ``CAM_READY_SLICE_S``. The server
        handles one request at a time, so one long WAIT_CAM_READY would hold off
        a RESET from the remote viewer for the whole wait, and a camera that was
        reset never becomes ready: a reset used to cost the full ``timeout``.
        An older server (no ``timed_out`` / ``reset_requested`` in its replies)
        still works: its slice timeouts are recognised by their error text.
        """
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise ValueError(
                    f"[LiveODClient] Camera ready timed out after {timeout:.0f} s."
                )
            slice_s = min(CAM_READY_SLICE_S, remaining)
            reply = self._send_recv(
                {"tag": "WAIT_CAM_READY", "timeout": slice_s},
                rcvtimeo_ms=int((slice_s + 5.0) * 1000),
            )
            if reply.get("reset_requested"):
                self.last_reset_requested = True
                return False
            if reply.get("ok") and reply.get("ready"):
                return True
            not_ready_yet = (reply.get("timed_out")
                             or "timeout" in str(reply.get("error", "")).lower())
            if not not_ready_yet:
                raise ValueError(
                    f"[LiveODClient] Camera ready failed: {reply.get('error')}"
                )

    def shot_complete(
        self, shot_idx: int, N_shots_total: int, xvar_values: dict
    ) -> bool:
        """Notify the server that a shot has completed.

        Returns True if the server has a pending reset request so the
        caller can abort the run at the shot boundary.

        Falls back to an explicit POLL if the server's SHOT_COMPLETE reply
        does not include ``reset_requested`` (older server builds that
        pre-date the field).
        """
        reply = self._send_recv(
            {
                "tag": "SHOT_COMPLETE",
                "shot_idx": shot_idx,
                "N_shots_total": N_shots_total,
                "xvar_values": xvar_values,
            }
        )
        self.last_adjust_values = reply.get('adjust_values', {})
        if "reset_requested" in reply:
            # cached for Scribe._check_for_abort_signal (top of the scan loop)
            self.last_reset_requested = bool(reply["reset_requested"])
            return self.last_reset_requested
        # Old server: reset_requested field not present — fall back to POLL.
        print("[LiveODClient] shot_complete: reply missing 'reset_requested' field — "
              "falling back to poll_reset() (liveOD GUI may need a restart).")
        return self.poll_reset()

    def end_run(self, payload: dict) -> bool:
        """Send END_RUN with final params and DataVault data.

        The server may take several seconds to write the HDF5 file — and if
        the data drive drops out it retries the save with backoff — so the
        receive timeout is raised to 10 minutes.  This must stay comfortably
        above the server's worst case (DATA_SAVER_TIMEOUT plus DataSaver's
        retry budget), or the client gives up on a save that is still running.
        """
        payload["tag"] = "END_RUN"
        reply = self._send_recv(payload, rcvtimeo_ms=600_000)
        if not reply.get("ok"):
            raise RuntimeError(
                f"[LiveODClient] END_RUN failed: {reply.get('error')}"
            )
        return True

    def abort_run(self) -> None:
        """Notify the server that the experiment has acknowledged the abort.

        Best-effort — all errors are suppressed because the experiment is
        already in the process of terminating and must not block.
        """
        try:
            self._send_recv({"tag": "ABORT_RUN"})
        except Exception:
            pass

    def poll_reset(self) -> bool:
        """Ask the server if a reset has been requested.

        Called as an RPC between shots. Returns True if the experiment
        should abort. Returns False on any network error so a transient
        glitch doesn't kill the run.
        """
        try:
            reply = self._send_recv({"tag": "POLL"})
            if not reply.get("ok", False):
                # Server returned an error — likely an old build that doesn't
                # recognise the POLL tag.  Warn once so the user knows.
                print(f"[LiveODClient] poll_reset: unexpected server reply: {reply}"
                      "\n  → liveOD GUI may need to be restarted to pick up new code.")
            return bool(reply.get("reset_requested", False))
        except Exception as exc:
            print(f"[LiveODClient] poll_reset: network error (returning False): {exc}")
            return False

    def close(self):
        """Release ZMQ resources."""
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
        try:
            self._context.term()
        except Exception:
            pass
