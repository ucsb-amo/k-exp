"""Fetching diagnostic frames from liveOD.

liveOD's broadcast only announces a pushed frame (AUX_NOTICE, no array); the
latest array of each key is GET_AUX_DATA's on its REP port. One thread asks
for the keys that were announced, merging requests that arrive while one is
in flight, so the viewer never queues up behind itself on liveOD's REP thread
(the one the experiment's own requests go through).
"""
from __future__ import annotations

import pickle
import threading

import zmq
from PyQt6.QtCore import QThread, pyqtSignal


def discover_endpoint(base_id, timeout=3.0):
    """(ip, port) of liveOD's ``base_id`` beacon on this lab's hardware, or None."""
    from waxx.util.comms_server.hardware_id import discover_scoped  # noqa: PLC0415
    return discover_scoped(base_id, timeout=timeout)


class AuxFetcher(QThread):
    """``request(keys)`` from any thread; ``fetched`` carries GET_AUX_DATA's
    ``items`` (key -> {run_id, key, index, array, t})."""

    fetched = pyqtSignal(object)
    status = pyqtSignal(str)

    TIMEOUT_MS = 5000

    def __init__(self, endpoint=None, parent=None):
        super().__init__(parent)
        self._endpoint = endpoint           # (ip, port); None: discovered
        self._lock = threading.Lock()
        self._pending = set()
        self._wake = threading.Event()
        self._running = True

    def request(self, keys):
        with self._lock:
            self._pending.update(keys)
        self._wake.set()

    def stop(self):
        self._running = False
        self._wake.set()

    def run(self):
        ctx = zmq.Context()
        try:
            while self._running:
                self._wake.wait(0.5)
                self._wake.clear()
                with self._lock:
                    keys, self._pending = sorted(self._pending), set()
                if not keys or not self._running:
                    continue
                if self._endpoint is None:
                    self._endpoint = discover_endpoint("live_od")
                    if self._endpoint is None:
                        self.status.emit("liveOD server not found")
                        self.request(keys)          # try again later
                        self._wake.clear()
                        self._sleep(2.0)
                        continue
                try:
                    reply = self._ask(ctx, {"tag": "GET_AUX_DATA", "keys": keys})
                except Exception as exc:
                    self.status.emit(f"GET_AUX_DATA failed: {exc}")
                    self._endpoint = None           # rediscover: liveOD may have moved
                    self._sleep(1.0)
                    continue
                if not reply.get("ok"):
                    self.status.emit(f"GET_AUX_DATA: {reply.get('error', 'refused')}")
                    continue
                self.fetched.emit(dict(reply.get("items") or {}))
        finally:
            ctx.term()

    def _ask(self, ctx, msg):
        ip, port = self._endpoint
        sock = ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.SNDTIMEO, 3000)
        sock.setsockopt(zmq.RCVTIMEO, self.TIMEOUT_MS)
        sock.setsockopt(zmq.LINGER, 0)
        try:
            sock.connect(f"tcp://{ip}:{port}")
            sock.send(pickle.dumps(msg))
            return pickle.loads(sock.recv())
        finally:
            sock.close()

    def _sleep(self, s):
        """Sleep, but wake at once for stop()."""
        t = 0.0
        while self._running and t < s:
            self.msleep(100)
            t += 0.1


__all__ = ["AuxFetcher", "discover_endpoint"]
