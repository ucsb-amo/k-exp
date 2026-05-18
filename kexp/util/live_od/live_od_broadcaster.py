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

import zmq
from PyQt6.QtCore import QThread


class LiveODBroadcaster(QThread):
    """Thread-safe ZMQ PUB broadcaster.

    Uses an internal queue so that Qt signal callbacks (which run on the
    GUI thread) can safely enqueue messages without touching the ZMQ socket
    directly — ZMQ sockets are not thread-safe.
    """

    def __init__(self, port: int):
        super().__init__()
        self._port = port
        self._queue: queue.Queue = queue.Queue()
        self._running = False

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.PUB)
        socket.bind(f"tcp://*:{self._port}")
        self._running = True
        print(f"[LiveODBroadcaster] Publishing on tcp://*:{self._port}")
        try:
            while self._running:
                try:
                    msg = self._queue.get(timeout=0.5)
                    socket.send(pickle.dumps(msg), zmq.NOBLOCK)
                except queue.Empty:
                    continue
                except Exception as exc:
                    print(f"[LiveODBroadcaster] send error: {exc}")
        finally:
            socket.close()
            context.term()

    def stop(self):
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

    def broadcast_run_started(self, run_id: int):
        self._enqueue({'tag': 'RUN_STARTED', 'run_id': int(run_id)})

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
        """
        img_atoms, img_light, img_dark, od, sum_od_x, sum_od_y = plot_data
        self._enqueue({
            'tag': 'OD_IMAGE',
            'img_atoms': img_atoms,
            'img_light': img_light,
            'img_dark': img_dark,
            'od': od,
            'sum_od_x': sum_od_x,
            'sum_od_y': sum_od_y,
        })

    def broadcast_run_done(self):
        self._enqueue({'tag': 'RUN_DONE'})
