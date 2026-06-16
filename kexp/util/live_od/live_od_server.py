"""
ZMQ REP server running inside the liveOD GUI process.

Receives INIT_RUN / WAIT_CAM_READY / SHOT_COMPLETE / END_RUN messages
from the experiment client (possibly on a different machine) and
coordinates HDF5 file creation, camera spawning, and final data saving.

The server runs as a QThread to stay compatible with PyQt6 event dispatch
on the GUI machine. All HDF5 I/O stays on the server side; the experiment
client never needs the data drive mounted.
"""

import pickle
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import zmq
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from waxx.util.comms_server.waxx_server import WaxxServer


class LiveODServer(QThread, WaxxServer):
    """ZMQ REP server embedded in the liveOD process.

    Listens for messages from the experiment client and drives file I/O
    and camera management.

    Signals
    -------
    new_run_signal(filepath, camera_key, capture_images, save_data, imaging_type, n_img, n_shots, n_pwa_per_shot)
        Emitted after INIT_RUN.  ``filepath`` is ``""`` when
        ``save_data=False``.  ``capture_images`` indicates whether a
        CameraBaby should be spawned.  ``n_img``, ``n_shots``, and
        ``n_pwa_per_shot`` carry the image-count params from the payload so
        ``DataHandler`` can be initialised correctly even when
        ``save_data=False`` (and no HDF5 file is read).
    shot_progress_signal(shot_idx, N_shots_total, xvar_values_dict)
        Emitted for each SHOT_COMPLETE message.
    run_done_signal()
        Emitted after END_RUN is fully handled.
    """

    new_run_signal = pyqtSignal(str, str, bool, bool, int, int, int, int, object, object, object)   # filepath, camera_key, capture_images, save_data, imaging_type, n_img, n_shots, n_pwa_per_shot, camera_params, params_payload, run_info_payload
    shot_progress_signal = pyqtSignal(int, int, object)       # shot_idx, N_total, xvar_values dict
    run_done_signal = pyqtSignal()
    run_started_signal = pyqtSignal(int, object)               # run_id, xvarnames (emitted after INIT_RUN, before new_run_signal)
    reset_signal = pyqtSignal()                               # triggered by remote RESET command
    camera_control_signal = pyqtSignal(str, str)              # camera_key, action ('open'|'close'|'toggle')

    def __init__(self, server_talk, data_saver, port: int = 0):
        super().__init__()  # QThread.__init__
        WaxxServer.__init__(self, "live_od", port)  # explicit — avoids MRO conflict
        self._server_talk = server_talk
        self._data_saver = data_saver
        self._ip = "0.0.0.0"
        self._port = port
        self._cam_ready_event = threading.Event()
        self._data_handler_done_event = threading.Event()
        self._data_handler_done_event.set()  # default: no DataHandler in flight
        self._file_creation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="liveod_file_create")
        self._running = False
        self._current_save_data = False
        self._current_capture_images = False
        self._current_filepath = ""
        self._current_run_id = 0
        self._reset_requested = False   # set by RESET; cleared by next INIT_RUN
        self._run_in_progress = False   # True between INIT_RUN and END_RUN/ABORT
        self._shot_timestamps: list = []  # Unix timestamps (s) recorded server-side on each SHOT_COMPLETE
        self._scalar_subscriber_count: dict = {}  # tier -> subscriber count
        self._scalar_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public slots (safe to call from any thread)
    # ------------------------------------------------------------------

    def on_cam_ready(self):
        """Set camera-ready event.

        Connect this to ``CameraBaby.cam_status_signal`` filtered to
        status == 2 using ``Qt.ConnectionType.DirectConnection`` so the
        threading.Event is set from the CameraBaby thread immediately.
        """
        self._cam_ready_event.set()

    def on_data_handler_done(self):
        """Set the data-handler-done event.

        Connect to ``DataHandler.done_writing_signal`` with
        ``Qt.ConnectionType.DirectConnection`` so the event is set from
        the DataHandler thread immediately after it closes the HDF5 file.
        """
        self._data_handler_done_event.set()

    def stop(self):
        """Request the server loop to stop on the next poll cycle."""
        self._stop_beacon()
        self._running = False

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        actual_port = socket.bind_to_random_port("tcp://0.0.0.0")
        self._port = actual_port
        self._waxx_port = actual_port   # sync beacon port before _start_beacon()
        socket.setsockopt(zmq.RCVTIMEO, 500)   # 500 ms poll so we can honour stop()
        self._running = True
        self._start_beacon()
        print(f"[LiveODServer] Listening on tcp://0.0.0.0:{self._port}")
        try:
            while self._running:
                try:
                    raw = socket.recv()
                except zmq.Again:
                    continue          # poll timeout — loop to check _running

                tag = "<unknown>"
                try:
                    msg = pickle.loads(raw)
                    tag = msg.get("tag", "")
                    if tag == "INIT_RUN":
                        reply = self._handle_init_run(msg)
                    elif tag == "WAIT_CAM_READY":
                        reply = self._handle_wait_cam_ready(msg)
                    elif tag == "SHOT_COMPLETE":
                        reply = self._handle_shot_complete(msg)
                    elif tag == "END_RUN":
                        reply = self._handle_end_run(msg)
                    elif tag == "RESET":
                        reply = self._handle_reset(msg)
                    elif tag == "CAMERA_CONTROL":
                        reply = self._handle_camera_control(msg)
                    elif tag == "POLL":
                        reply = self._handle_poll(msg)
                    elif tag == "ABORT_RUN":
                        reply = self._handle_abort_run(msg)
                    elif tag == "SUBSCRIBE_SCALARS":
                        reply = self._handle_subscribe_scalars(msg)
                    elif tag == "UNSUBSCRIBE_SCALARS":
                        reply = self._handle_unsubscribe_scalars(msg)
                    else:
                        reply = {"ok": False, "error": f"Unknown tag: {tag}"}
                except Exception as exc:
                    reply = {"ok": False, "error": str(exc)}
                    import traceback
                    print(f"[LiveODServer] Error handling {tag!r}:")
                    traceback.print_exc()

                socket.send(pickle.dumps(reply))
        finally:
            socket.close()
            context.term()

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def _finalize_reset_run(self, notify_gui: bool = True):
        """Finalize a reset-aborted run.

        This is called either when the experiment explicitly sends ABORT_RUN,
        or opportunistically on the next INIT_RUN if the experiment process was
        killed and never sent that confirmation.

        ``notify_gui`` controls whether ``reset_signal`` is emitted to drive
        ``main_window.reset()``.  Set it to False when the GUI was already
        notified by the original ``_handle_reset`` call — re-emitting would
        race with the next ``INIT_RUN`` and cause ``main_window.reset()`` to
        set ``_reset_requested = True`` after the new run has already started,
        aborting the new run on its first poll.
        """
        # Emit reset_signal so the GUI's reset() handler interrupts the
        # DataHandler and CameraBaby.  This sets data_handler.interrupted=True
        # and calls data_handler.quit(), which causes the DataHandler to close
        # its HDF5 handle and emit done_writing_signal — which in turn sets
        # _data_handler_done_event.  Must happen BEFORE the wait below.
        # Only emit when a camera run is active: for no-camera runs there is
        # no DataHandler or CameraBaby to clean up, and reset() would
        # incorrectly call update_run_id() (no active baby → else branch).
        if notify_gui and self._current_capture_images:
            self.reset_signal.emit()
        # Delete the HDF5 file if it still exists (may already be gone for
        # camera runs whose CameraBaby called dishonorable_death).
        if self._current_filepath and os.path.exists(self._current_filepath):
            # Wait for the DataHandler (camera writer) to close its HDF5
            # handle before attempting deletion.  Without this the file is
            # still open and os.remove raises WinError 32 on Windows.
            if not self._data_handler_done_event.wait(timeout=30.0):
                print("[LiveODServer] WARNING: DataHandler did not release the file within 30 s — deletion may fail.")
            try:
                os.remove(self._current_filepath)
                print(f"Deleted incomplete data file: {self._current_filepath}")
            except Exception as exc:
                print(f"Warning: could not delete incomplete data file: {exc}")
            self._current_filepath = ""
        self._reset_requested = False
        self._run_in_progress = False
        self.run_done_signal.emit()

    def _handle_init_run(self, msg: dict) -> dict:
        # If the previous run was reset but the experiment process was killed
        # before sending ABORT_RUN, finalize that reset now. This keeps the
        # next run start non-blocking and stateless.  The GUI was already
        # notified by the original _handle_reset call, so don't re-emit
        # reset_signal — that would race with this INIT_RUN and cause the
        # new run to abort on its first poll.
        if self._reset_requested:
            self._finalize_reset_run(notify_gui=False)

        save_data = bool(msg.get("save_data", False))
        capture_images = bool(msg.get("capture_images", False))
        camera_key = str(msg.get("camera_key", ""))
        imaging_type = int(msg.get("imaging_type", 0))

        camera_params = msg.get('camera_params', {})
        self._cam_ready_event.clear()
        self._current_save_data = save_data
        self._current_capture_images = capture_images
        # Gate END_RUN saves on DataHandler finishing.  For no-camera runs
        # there is no DataHandler, so mark it done immediately.
        self._data_handler_done_event.clear()
        if not capture_images:
            self._data_handler_done_event.set()

        run_id = 0
        filepath = ""

        if save_data:
            run_id = self._server_talk.get_run_id()
            # Compute the filepath immediately (pure string ops, no I/O).
            filepath = self._data_saver.compute_data_filepath_from_payload(msg, run_id)
            # Create the HDF5 file on a background thread so the ZMQ REP
            # socket can reply at once and not block the experiment client.
            # DataHandler.wait_for_data_available() already polls until the
            # file exists, so the delay is handled transparently.
            self._file_creation_executor.submit(
                self._data_saver.create_data_file_from_payload, msg, run_id
            )

        self._current_filepath = filepath
        self._current_run_id = run_id
        self._reset_requested = False
        self._run_in_progress = True
        self._shot_timestamps = []       # reset per-run timestamp list

        n_img = int(msg.get('params', {}).get('N_img', 1))
        n_shots = int(msg.get('N_shots_with_repeats', 1))
        n_pwa = int(msg.get('N_pwa_per_shot', 1))

        params_payload = dict(msg.get('params', {}))
        run_info_payload = {
            'imaging_type': imaging_type,
            'save_data': int(msg.get('save_data_flag', int(save_data))),
            'run_date_str': str(msg.get('run_date_str', '')),
            'run_datetime_str': str(msg.get('run_datetime_str', '')),
            'expt_class': str(msg.get('expt_class', '')),
            'xvarnames': list(msg.get('xvarnames', [])),
        }

        self.run_started_signal.emit(run_id, list(run_info_payload.get('xvarnames', [])))
        self.new_run_signal.emit(filepath, camera_key, capture_images, save_data, imaging_type, n_img, n_shots, n_pwa, camera_params, params_payload, run_info_payload)
        print(
            f"[LiveODServer] INIT_RUN: run_id={run_id}, "
            f"save={save_data}, cam={capture_images}"
        )
        return {"ok": True, "run_id": run_id, "filepath": filepath}

    def _handle_wait_cam_ready(self, msg: dict) -> dict:
        timeout = float(msg.get("timeout", 60.0))
        ready = self._cam_ready_event.wait(timeout=timeout)
        if not ready:
            return {"ok": False, "ready": False, "error": "Camera ready timeout"}
        return {"ok": True, "ready": True}

    def _handle_shot_complete(self, msg: dict) -> dict:
        self._shot_timestamps.append(time.time())
        shot_idx = int(msg.get("shot_idx", 0))
        N_total = int(msg.get("N_shots_total", 1))
        xvar_values = msg.get("xvar_values", {})
        self.shot_progress_signal.emit(shot_idx, N_total, xvar_values)
        if not self._current_capture_images:
            print(f"[LiveODServer] shot {shot_idx + 1}/{N_total}")
        # Include reset flag so the experiment can abort at shot boundary
        # even if the POLL-based check misses it.
        return {"ok": True, "reset_requested": self._reset_requested}

    def _handle_end_run(self, msg: dict) -> dict:
        if self._reset_requested:
            print(f"[LiveODServer] END_RUN: run {self._current_run_id} was reset — discarding data.")
            if self._current_filepath and os.path.exists(self._current_filepath):
                try:
                    os.remove(self._current_filepath)
                    print(f"[LiveODServer] Deleted data file: {self._current_filepath}")
                except Exception as exc:
                    print(f"[LiveODServer] Warning: could not delete data file: {exc}")
            self._reset_requested = False
            self._run_in_progress = False
            self.run_done_signal.emit()
            return {"ok": True}
        if self._current_save_data and self._current_filepath:
            # Wait for DataHandler to close its HDF5 handle before we open
            # the same file for the end-of-run save.  Without this wait the
            # two h5py opens race and either corrupt the file or raise OSError.
            if not self._data_handler_done_event.wait(timeout=60.0):
                print("[LiveODServer] WARNING: DataHandler did not finish within 60 s — proceeding anyway.")
            try:
                self._data_saver.save_data_from_payload(
                    msg, self._current_filepath,
                    shot_timestamps=self._shot_timestamps,
                )
                print(f"[LiveODServer] END_RUN: run_id={self._current_run_id} saved.")
                # Clear filepath so a late RESET cannot delete an already-saved file.
                self._current_filepath = ""
            except Exception as exc:
                import traceback
                print(f"[LiveODServer] END_RUN: save failed:")
                traceback.print_exc()
                return {"ok": False, "error": str(exc)}
        else:
            print("[LiveODServer] END_RUN: save_data=False, nothing written.")

        self._run_in_progress = False
        self.run_done_signal.emit()
        return {"ok": True}

    def _handle_reset(self, msg: dict) -> dict:
        print("[LiveODServer] RESET requested by remote viewer.")
        self._reset_requested = True
        self.reset_signal.emit()
        return {"ok": True}

    def _handle_camera_control(self, msg: dict) -> dict:
        camera_key = str(msg.get("camera_key", ""))
        action = str(msg.get("action", "toggle"))
        if action not in ("open", "close", "toggle"):
            return {"ok": False, "error": f"Unknown camera action: {action}"}
        if not camera_key:
            return {"ok": False, "error": "Missing camera_key"}
        # Refuse camera open/close/toggle during an active run.  Closing a
        # camera being driven by a CameraBaby crashes the grab loop
        # (dishonorable_death); opening any camera blocks the GUI thread
        # (Andor cooler init can take several seconds) and stalls all queued
        # SHOT_COMPLETE / RESET signals.
        if self._run_in_progress:
            print(f"[LiveODServer] CAMERA_CONTROL rejected ({camera_key} -> {action}): run in progress")
            return {"ok": False, "error": "Camera control rejected: run in progress"}
        print(f"[LiveODServer] CAMERA_CONTROL: {camera_key} -> {action}")
        self.camera_control_signal.emit(camera_key, action)
        return {"ok": True}

    def _handle_abort_run(self, msg: dict) -> dict:
        """Experiment has acknowledged the abort — clean up and close out the run."""
        print("Experiment acknowledged: run aborted.")
        # If _reset_requested is True, the viewer's _handle_reset already
        # emitted reset_signal and the GUI ran main_window.reset().  Re-emitting
        # reset_signal here would queue a second main_window.reset() that races
        # with the next INIT_RUN: when save_data=False, INIT_RUN is fast enough
        # to return (clearing _reset_requested) before that queued reset() runs,
        # and reset()'s unconditional `_reset_requested = True` then aborts the
        # new run on its first poll.  Only emit reset_signal if no prior RESET
        # set the flag (e.g. RTIOUnderflow path, where the experiment aborts
        # itself without going through _handle_reset).
        gui_already_notified = self._reset_requested
        self._finalize_reset_run(notify_gui=not gui_already_notified)
        self._reset_requested = False
        return {"ok": True}

    def _handle_poll(self, msg: dict) -> dict:
        """Lightweight poll — lets the experiment check for a pending reset."""
        return {"ok": True, "reset_requested": self._reset_requested}

    def _handle_subscribe_scalars(self, msg: dict) -> dict:
        """Remote viewer subscribes to scalar compute tier."""
        tier = str(msg.get('tier', 'atom_number'))
        if tier not in ('atom_number', 'fits'):
            return {"ok": False, "error": f"Unknown tier: {tier}"}
        with self._scalar_lock:
            self._scalar_subscriber_count[tier] = self._scalar_subscriber_count.get(tier, 0) + 1
        return {"ok": True}

    def _handle_unsubscribe_scalars(self, msg: dict) -> dict:
        """Remote viewer unsubscribes from scalar compute tier."""
        tier = str(msg.get('tier', 'atom_number'))
        with self._scalar_lock:
            count = self._scalar_subscriber_count.get(tier, 0)
            self._scalar_subscriber_count[tier] = max(0, count - 1)
        return {"ok": True}

    def get_requested_metrics(self) -> set:
        """Return set of tiers currently requested by any subscriber.

        Called from the Analyzer thread — reads under lock for safety.
        """
        with self._scalar_lock:
            return {
                tier
                for tier, count in self._scalar_subscriber_count.items()
                if count > 0
            }

    def register_scalar_subscription(self, tier: str):
        """In-process subscription (local scalar plot window)."""
        if tier not in ('atom_number', 'fits'):
            return
        with self._scalar_lock:
            self._scalar_subscriber_count[tier] = self._scalar_subscriber_count.get(tier, 0) + 1

    def unregister_scalar_subscription(self, tier: str):
        """In-process unsubscription (local scalar plot window)."""
        with self._scalar_lock:
            count = self._scalar_subscriber_count.get(tier, 0)
            self._scalar_subscriber_count[tier] = max(0, count - 1)
