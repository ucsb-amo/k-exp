"""interlock_client.py — thin TCP wrapper for the interlock server.

Uses WaxxClient for UDP service discovery, then a simple line+JSON wire
protocol matching ``interlock_server.py``.
"""

from __future__ import annotations

import json
import logging
import socket
from typing import Any, Optional

from waxx.util.comms_server.waxx_client import WaxxClient


_LOG = logging.getLogger("kexp.dashboard.client.interlock")


class InterlockClient(WaxxClient):
    """Discovery + RPC.  Short timeouts (Threat 9: never block UI)."""

    SERVER_ID = "interlock"

    def __init__(
        self,
        discovery_timeout: float = 3.0,
        timeout: float = 1.5,
    ):
        super().__init__(self.SERVER_ID, discovery_timeout=discovery_timeout)
        self.timeout = float(timeout)

    # ------------------------------------------------------------------
    # Wire helpers
    # ------------------------------------------------------------------

    def _send(self, command: str) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(self.timeout)
            try:
                s.connect((self.host, self.port))
            except OSError as exc:
                # Try one rediscovery in case the server restarted on a new port.
                if not self._rediscover(timeout=1.0):
                    raise
                s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s2.settimeout(self.timeout)
                try:
                    s2.connect((self.host, self.port))
                    return self._roundtrip(s2, command)
                finally:
                    s2.close()
            return self._roundtrip(s, command)

    def _roundtrip(self, sock: socket.socket, command: str) -> str:
        sock.sendall((command + "\n").encode("utf-8"))
        buf = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b"\n") or len(buf) > 1_000_000:
                break
        return buf.decode("utf-8", errors="replace").strip()

    def _send_json(self, command: str) -> dict:
        raw = self._send(command)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            _LOG.warning("interlock: non-JSON response to %s: %r", command, raw[:200])
            return {"status": "error", "message": f"bad response: {exc}", "raw": raw}
        if not isinstance(obj, dict):
            return {"status": "error", "message": "expected dict response", "raw": obj}
        return obj

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict:
        return self._send_json("GET_SNAPSHOT")

    def reset_interlock(self) -> dict:
        return self._send_json("RESET_INTERLOCK")

    def enable_magnets(self) -> dict:
        return self._send_json("ENABLE_MAGNETS")

    def disable_magnets(self) -> dict:
        return self._send_json("DISABLE_MAGNETS")

    def flush_csv(self) -> dict:
        return self._send_json("FLUSH_CSV")


__all__ = ["InterlockClient"]
