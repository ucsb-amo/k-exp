"""
ZMQ PUB broadcaster running inside the LiveOD Server process.

Publishes real-time run events (OD images, shot progress, run lifecycle)
on a separate port so that any number of RemoteViewerWindows can subscribe
and display live progress without needing access to the data drive or
being on the server machine.

Message format — every message is a pickled dict with a 'tag' key:

    {'tag': 'RUN_STARTED',  'run_id': int}
    {'tag': 'SHOT_PROGRESS','shot_idx': int, 'N_total': int,
                             'xvar_values': dict}
    {'tag': 'OD_IMAGE',     'img_atoms': ndarray, 'img_light': ndarray,
                             'img_dark': ndarray, 'od': ndarray,
                             'sum_od_x': ndarray, 'sum_od_y': ndarray}
    {'tag': 'RUN_DONE'}
"""

import pickle
import queue
import time

import numpy as np
import zmq
from PyQt6.QtCore import QThread
from waxx.util.comms_server.waxx_server import WaxxServer
from waxx.util.comms_server.hardware_id import scoped_server_id


# Heartbeat interval (s) — sent when the broadcaster queue is idle so that
# late-joining subscribers cross the PUB/SUB slow-joiner gap and can flip
# their UI to "connected" without waiting for a real OD_IMAGE.
_HEARTBEAT_INTERVAL_S = 0.5

# ZMQ high-water mark — drop oldest frames when the pipeline backs up rather
# than accumulating latency. 8 frames covers ~1 s of backlog at 8 Hz.
_SNDHWM = 8


class LiveODBroadcaster(QThread, WaxxServer):
    """Thread-safe ZMQ PUB broadcaster.

    Uses an internal queue so that Qt signal callbacks (which run on the
    GUI thread) can safely enqueue messages without touching the ZMQ socket
    directly — ZMQ sockets are not thread-safe.

    Broadcasts a service-discovery beacon under server_id ``'live_od_broadcast'``
    so that RemoteViewerWindow instances can discover the publish port via UDP.
    """

    def __init__(self):
        super().__init__()  # QThread.__init__
        WaxxServer.__init__(self, scoped_server_id("live_od_broadcast"), 0)  # port updated in run()
        self._queue: queue.Queue = queue.Queue()
        self._running = False

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.PUB)
        socket.setsockopt(zmq.SNDHWM, _SNDHWM)
        actual_port = socket.bind_to_random_port("tcp://*")
        self._port = actual_port
        self._waxx_port = actual_port
        self._start_beacon()
        self._running = True
        print(f"[LiveODBroadcaster] Publishing on tcp://*:{self._port}")
        last_send = time.monotonic()
        try:
            while self._running:
                try:
                    msg = self._queue.get(timeout=_HEARTBEAT_INTERVAL_S)
                    socket.send(pickle.dumps(msg), zmq.NOBLOCK)
                    last_send = time.monotonic()
                except queue.Empty:
                    # Idle — emit a lightweight HELLO so subscribers know the
                    # link is alive (defeats PUB/SUB slow-joiner silence).
                    if time.monotonic() - last_send >= _HEARTBEAT_INTERVAL_S:
                        try:
                            socket.send(
                                pickle.dumps({'tag': 'HELLO', 't_send': time.time()}),
                                zmq.NOBLOCK,
                            )
                        except Exception:
                            pass
                        last_send = time.monotonic()
                    continue
                except Exception as exc:
                    print(f"[LiveODBroadcaster] send error: {exc}")
        finally:
            socket.close()
            context.term()

    def stop(self):
        self._stop_beacon()
        self._running = False

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _enqueue(self, msg: dict):
        try:
            self._queue.put_nowait(msg)
        except queue.Full:
            pass

    # ------------------------------------------------------------------
    # Public broadcast methods — safe to call from any thread / Qt slot
    # ------------------------------------------------------------------

    def broadcast_run_started(self, run_id: int, xvarnames: object = None):
        self._enqueue({
            'tag': 'RUN_STARTED',
            'run_id': int(run_id),
            'xvarnames': list(xvarnames) if xvarnames else [],
        })

    def broadcast_shot_progress(self, shot_idx: int, N_total: int,
                                 xvar_values: object):
        self._enqueue({
            'tag': 'SHOT_PROGRESS',
            'shot_idx': int(shot_idx),
            'N_total': int(N_total),
            'xvar_values': dict(xvar_values) if xvar_values else {},
        })

    def broadcast_od_image(self, plot_data: tuple):
        """Broadcast one analyzed shot.

        ``plot_data`` is the tuple produced by ``Analyzer.analyze()``:
        ``(img_atoms, img_light, img_dark, od, sum_od_x, sum_od_y)``.

        Raw camera frames are kept in their native uint16; OD arrays are
        downcast to float32 before transmission. This is a display-only
        downcast — the HDF5 save path on the server is untouched.
        """
        img_atoms, img_light, img_dark, od, sum_od_x, sum_od_y = plot_data
        self._enqueue({
            'tag': 'OD_IMAGE',
            't_capture': time.time(),
            'img_atoms': img_atoms,
            'img_light': img_light,
            'img_dark': img_dark,
            'od': np.asarray(od, dtype=np.float32),
            'sum_od_x': np.asarray(sum_od_x, dtype=np.float32),
            'sum_od_y': np.asarray(sum_od_y, dtype=np.float32),
        })

    def broadcast_run_done(self):
        self._enqueue({'tag': 'RUN_DONE'})

    def broadcast_shot_scalars(self, scalars: dict):
        """Broadcast per-shot scalar quantities to remote viewers.

        ``scalars`` is the dict emitted by ``Analyzer.shot_scalars_signal``.
        NaN values are kept as-is (receivers should handle them gracefully).
        """
        self._enqueue({'tag': 'SHOT_SCALARS', **scalars})

    def broadcast_fk_tof(self, data: dict):
        """Broadcast per-shot FK TOF widths to remote viewers.

        ``data`` is the dict emitted by ``Analyzer.fk_tof_signal``.
        """
        self._enqueue({'tag': 'FK_TOF', **data})

    def broadcast_log_msg(self, text: str):
        self._enqueue({'tag': 'LOG_MSG', 'text': str(text)})

    def broadcast_camera_state(self, states: dict):
        """Broadcast the current state of every camera button.

        ``states`` is a dict mapping camera_key -> one of
        ``'open' | 'closed' | 'loading' | 'failed' | 'grabbing'``.
        """
        self._enqueue({
            'tag': 'CAMERA_STATE',
            'states': {str(k): str(v) for k, v in states.items()},
        })

    def broadcast_adjust_values(self, values: dict):
        """Broadcast current adjust-parameter values to remote viewers."""
        if values:
            self._enqueue({'tag': 'ADJUST_VALUES', 'values': dict(values)})
