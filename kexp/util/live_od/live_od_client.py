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

import zmq

from waxx.util.comms_server.waxx_client import WaxxClient
from waxx.util.comms_server.hardware_id import resolve_scoped_server_id


class LiveODClient(WaxxClient):
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

        Delegates to ``WaxxClient._rediscover()`` then syncs the ZMQ
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
        """Send INIT_RUN.  Returns ``{"run_id": int, "filepath": str}``."""
        payload["tag"] = "INIT_RUN"
        reply = self._send_recv(payload)
        if not reply.get("ok"):
            raise RuntimeError(
                f"[LiveODClient] INIT_RUN failed: {reply.get('error')}"
            )
        return reply

    def wait_cam_ready(self, timeout: float = 60.0) -> bool:
        """Block until liveOD confirms the camera is ready.

        ``timeout`` (seconds) is forwarded to the server so it can give up
        instead of blocking forever.  The socket receive timeout is
        extended by 5 s on top to allow for network latency.
        """
        reply = self._send_recv(
            {"tag": "WAIT_CAM_READY", "timeout": timeout},
            rcvtimeo_ms=int((timeout + 5.0) * 1000),
        )
        if not reply.get("ok") or not reply.get("ready"):
            raise ValueError(
                f"[LiveODClient] Camera ready timed out or failed: "
                f"{reply.get('error')}"
            )
        return True

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
        if "reset_requested" in reply:
            return bool(reply["reset_requested"])
        # Old server: reset_requested field not present — fall back to POLL.
        print("[LiveODClient] shot_complete: reply missing 'reset_requested' field — "
              "falling back to poll_reset() (liveOD GUI may need a restart).")
        return self.poll_reset()

    def end_run(self, payload: dict) -> bool:
        """Send END_RUN with final params and DataVault data.

        The server may take several seconds to write the HDF5 file, so
        the receive timeout is raised to 5 minutes.
        """
        payload["tag"] = "END_RUN"
        reply = self._send_recv(payload, rcvtimeo_ms=300_000)
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
