import sys
from queue import Queue
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStyle
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
import time
import names

from waxa import ROI
from waxa.data import DataSaver

from kexp.util.live_od.camera_mother import CameraMother, CameraBaby, DataHandler, CameraNanny
from kexp.util.live_od.camera_connection_widget import CamConnBar
from kexp.util.live_od.gui.viewer import LiveODViewer
from kexp.util.live_od.gui.analyzer import Analyzer
from kexp.util.live_od.gui.plotter import LiveODPlotter
from kexp.util.live_od.live_od_server import LiveODServer
from kexp.util.live_od.live_od_broadcaster import LiveODBroadcaster
from kexp.util.live_od.gui.live_scalar_plot_window import LiveScalarPlotWindow

class LiveODWindow(QWidget):
    interrupt = pyqtSignal()
    def __init__(self):

        super().__init__()

        from kexp.config.ip import server_talk, PATHS
        self.server_talk = server_talk

        self.queue = Queue()
        self.camera_nanny = CameraNanny()
        # CameraMother is kept as a no-op stub for import compatibility.
        self.camera_mother = CameraMother(output_queue=self.queue,
                                          camera_nanny=self.camera_nanny,
                                          server_talk=self.server_talk)

        self.the_baby = None
        self.data_handler = None
        self.last_camera = ""
        self.img_count = 0
        self.img_count_run = 0
        self._run_active = False   # True between INIT_RUN and END_RUN/reset
        self._run_was_reset = False  # True when reset() kills an active no-camera run
        self.setup_widgets()
        self.setup_layout()

        # ZMQ REP server — drives all run lifecycle events.
        self.data_saver = DataSaver(*PATHS, server_talk=self.server_talk)
        self.live_od_server = LiveODServer(
            self.server_talk, self.data_saver,
            0,
        )
        self.live_od_server.new_run_signal.connect(self.spawn_baby)
        self.live_od_server.shot_progress_signal.connect(self.on_shot_progress)
        self.live_od_server.shot_progress_signal.connect(
            lambda _idx, _total, xvars: self.analyzer.set_xvar_values(xvars)
        )
        self.live_od_server.shot_timing_signal.connect(self.on_shot_timing)
        self.live_od_server.run_done_signal.connect(self.on_run_done)
        self.live_od_server.reset_signal.connect(self.reset)
        self.live_od_server.camera_control_signal.connect(self.on_remote_camera_control)
        self.live_od_server.start()

        # Give the Analyzer a reference to the server for subscription queries
        self.analyzer.set_server(self.live_od_server)

        # ZMQ PUB broadcaster — forwards OD images and run events to remote viewers.
        self.broadcaster = LiveODBroadcaster()
        self.broadcaster.start()
        self.live_od_server.run_started_signal.connect(self.broadcaster.broadcast_run_started)
        self.live_od_server.shot_progress_signal.connect(self.broadcaster.broadcast_shot_progress)
        self.live_od_server.run_done_signal.connect(self.broadcaster.broadcast_run_done)
        self.analyzer.broadcast_signal.connect(self.broadcaster.broadcast_od_image)
        self.analyzer.shot_scalars_signal.connect(self.live_scalar_plot_window.on_shot_scalars)
        self.analyzer.shot_scalars_signal.connect(self.broadcaster.broadcast_shot_scalars)
        self.live_scalar_plot_window.subscription_changed_signal.connect(
            self._on_scalar_subscription_changed
        )

        # Broadcast camera-button state changes so remote viewers can mirror
        # the open/closed/grabbing UI.
        for btn in self.camera_conn_bar.buttons:
            btn.state_changed.connect(self._broadcast_camera_states)
        # Periodic re-broadcast so late-joining remote viewers learn current
        # state without needing to click anything.
        self._camera_state_timer = QTimer(self)
        self._camera_state_timer.timeout.connect(self._broadcast_camera_states)
        self._camera_state_timer.start(2000)
        # Initial broadcast (will reach any already-subscribed viewers).
        QTimer.singleShot(500, self._broadcast_camera_states)

    def _broadcast_camera_states(self, *_):
        try:
            self.broadcaster.broadcast_camera_state(
                self.camera_conn_bar.get_states())
        except Exception as e:
            print(f"[LiveODWindow] camera-state broadcast error: {e}")

    def on_remote_camera_control(self, camera_key: str, action: str):
        """Slot for ``LiveODServer.camera_control_signal``.

        Routes the request to the matching ``CameraButton`` on the local
        ``CamConnBar``.  Runs on the GUI thread (PyQt widget state is not
        thread-safe), but the server already refuses CAMERA_CONTROL while a
        run is in progress, so any blocking driver call here cannot stall
        SHOT_COMPLETE / RESET signals during acquisition.
        """
        btn = self.camera_conn_bar.get_button(camera_key)
        if btn is None:
            self.msg(f"Remote camera control: unknown camera {camera_key!r}")
            return
        try:
            if action == 'open':
                if not btn.camera.is_opened():
                    btn.open_camera()
            elif action == 'close':
                if btn.camera.is_opened():
                    btn.close_camera()
            else:  # toggle
                btn.button_pressed()
        except Exception as e:
            self.msg(f"Remote camera control error ({camera_key}/{action}): {e}")
        finally:
            self._broadcast_camera_states()

    def update_run_id_label(self):
        try:
            rid = self.server_talk.get_run_id()
            self.run_id_label.setText(f"Run ID: {rid}")
        except Exception as e:
            self.run_id_label.setText("Run ID: (unavailable)")

    def setup_widgets(self):
        self.server_talk.check_for_mapped_data_dir()

        self.viewer_window = LiveODViewer()
        self.setup_run_id_label()
        self.setup_eta_label()
        self.setup_output_window()
        self.setup_fix_button()
        self.camera_conn_bar = CamConnBar(self.camera_nanny, self.output_window)

        self.plotting_queue = Queue()
        self.analyzer = Analyzer(self.plotting_queue, self.viewer_window)
        self.plotter = LiveODPlotter(self.viewer_window, self.plotting_queue)
        self.plotter.start()

        # Scalar plot window — created once, shown on demand via Live Plot button
        self.live_scalar_plot_window = LiveScalarPlotWindow()
        self.viewer_window.live_plot_requested.connect(self._open_live_scalar_plot)

    def setup_screenshot_button(self):
        pass  # removed

    def setup_eta_label(self):
        self.eta_label = QLabel("ETA --:--")
        self.eta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.eta_label.setFont(font)
        self.eta_label.setStyleSheet("color: #444;")

    def setup_fix_button(self):
        self.fix_button = QPushButton('Reset')
        self.fix_button.setMinimumHeight(40)
        self.fix_button.setStyleSheet('background-color: #ffcccc; font-size: 40px; font-weight: bold;')
        self.fix_button.clicked.connect(self.reset)
        self.run_id_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def setup_output_window(self):
        font = QFont()
        font.setPointSize(10)
        self.output_window = self.viewer_window.output_window
        self.output_window.setFont(font)
        self.output_window.setReadOnly(True)

    def setup_run_id_label(self):
        # Add Run ID label
        self.run_id_label = QLabel()
        self.run_id_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.run_id_label.setFont(font)
        self.update_run_id_label()
        # Timer for periodic update
        self.run_id_timer = QTimer(self)
        self.run_id_timer.timeout.connect(self.update_run_id_label)
        self.run_id_timer.start(2000)  # 2 seconds

    def setup_layout(self):
        layout = QVBoxLayout()
        control_bar = QHBoxLayout()
        cam_bar = QVBoxLayout()
        run_id_row = QHBoxLayout()
        run_id_row.addWidget(self.eta_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        run_id_row.addWidget(self.run_id_label, 1, Qt.AlignmentFlag.AlignCenter)
        cam_bar.addLayout(run_id_row)
        cam_bar.addWidget(self.camera_conn_bar)
        control_bar.addLayout(cam_bar)
        control_bar.addWidget(self.fix_button)
        layout.addLayout(control_bar)
        layout.addWidget(self.viewer_window)
        self.setLayout(layout)
    
    # Slot to copy screenshot removed.

    def _open_live_scalar_plot(self):
        """Show the live scalar plot window, creating it if needed."""
        self.live_scalar_plot_window.show()
        self.live_scalar_plot_window.raise_()

    def _on_scalar_subscription_changed(self, old_tier, new_tier):
        """Update the server's subscription counters when the plot window changes metric or visibility."""
        if old_tier is not None:
            self.live_od_server.unregister_scalar_subscription(old_tier)
        if new_tier is not None:
            self.live_od_server.register_scalar_subscription(new_tier)

    def create_camera_baby(self, file, name):
        """Legacy stub — use spawn_baby via LiveODServer.new_run_signal."""
        self.spawn_baby(filepath=file, camera_key="",
                        capture_images=True, save_data=True,
                        imaging_type=0)

    def spawn_baby(self, filepath: str, camera_key: str,
                   capture_images: bool, save_data: bool,
                   imaging_type: int, n_img: int = 1,
                   n_shots: int = 1, n_pwa: int = 1,
                   camera_params: dict = None,
                   params_payload: dict = None,
                   run_info_payload: dict = None):
        """Spawn a new CameraBaby for an incoming run.

        Called from LiveODServer.new_run_signal (Qt queued connection so this
        always runs on the GUI thread).
        """
        name = names.get_first_name()
        self._run_name = name
        self._run_capture_images = capture_images
        self._run_was_reset = False

        self._run_active = True

        # Propagate run metadata to Analyzer and scalar plot window
        self.analyzer.set_camera_params(camera_params or {})
        self.analyzer.reset()
        self.viewer_window.set_camera_key(camera_key)
        self.eta_label.setText("ETA --:--")
        xvarnames = list(run_info_payload.get('xvarnames', [])) if run_info_payload else []
        self.live_scalar_plot_window.on_new_run(self.live_od_server._current_run_id, xvarnames)

        # Interrupt any DataHandler left over from the previous run.
        # On long runs the DataHandler thread can still be draining the shared
        # queue when the next INIT_RUN arrives.  If not interrupted here, the
        # old DataHandler consumes images placed by the new CameraBaby before
        # the new DataHandler has started, so the display never updates.
        if self.data_handler is not None:
            if self.data_handler.isRunning():
                self.msg("Warning: previous DataHandler still running — interrupting it.")
                self.data_handler.interrupted = True
                self.data_handler.wait(500)
            # Disconnect before replacing so a late SaveWorker from the
            # previous run can't falsely set _data_handler_done_event for
            # the new run, causing END_RUN to proceed before images are saved.
            try:
                self.data_handler.done_writing_signal.disconnect(
                    self.live_od_server.on_data_handler_done)
            except Exception:
                pass
            self.data_handler = None

        # Interrupt any CameraBaby left over from the previous run.
        # This happens when images never arrived (e.g. camera not triggered by
        # the remote machine's hardware) and the grab-loop timed out slowly, or
        # when on_run_done() was called before the baby finished its grab.
        if self.the_baby is not None and self.the_baby.isRunning():
            self.msg(f"Warning: previous CameraBaby still running — interrupting it.")
            try:
                self.the_baby.interrupted = True
            except Exception:
                pass
            self.the_baby = None
            self.data_handler = None

        if not capture_images:
            self.msg(f"{name}: I am born! (no camera, save_data={save_data})")
            self.the_baby = None
            self.data_handler = None
            return

        # Replace the shared queue with a fresh one for every camera run.
        # Without this, images left in the queue by an interrupted previous
        # DataHandler appear at the start of the new run — displayed as old-run
        # frames and (worse) written at indices 0, 1, … in the new HDF5 file.
        # Old objects (if still alive) keep their reference to the old queue.
        self.queue = Queue()

        self.data_handler = DataHandler(
            self.queue, data_filepath=filepath,
            save_data=save_data,
            imaging_type=imaging_type,
            camera_key=camera_key,
            camera_params=camera_params,
            params_payload=params_payload,
            run_info_payload=run_info_payload,
            n_img=n_img,
            n_shots=n_shots,
            n_pwa_per_shot=n_pwa,
        )
        self.the_baby = CameraBaby(self.data_handler, name, self.queue,
                                   self.camera_nanny)

        # Standard data/image wiring
        self.data_handler.save_data_bool_signal.connect(
            self.data_handler.get_save_data_bool)
        self.data_handler.image_type_signal.connect(
            self.analyzer.get_analysis_type)
        self.data_handler.got_image_from_queue.connect(self.analyzer.got_img)
        self.data_handler.got_image_from_queue.connect(self.count_images)

        self.the_baby.camera_connect.connect(self.check_new_camera)
        self.the_baby.camera_grab_start.connect(self.grab_start_msg)
        self.the_baby.camera_grab_start.connect(self.get_img_number)
        self.the_baby.camera_grab_start.connect(self.data_handler.get_img_number)
        self.the_baby.camera_grab_start.connect(self.viewer_window.get_img_number)
        self.the_baby.camera_grab_start.connect(self.analyzer.get_img_number)
        self.the_baby.camera_grab_start.connect(self.data_handler.start)
        self.the_baby.camera_grab_start.connect(self.reset_count)

        self.the_baby.honorable_death_signal.connect(
            lambda: self.msg(f'Run complete. {name} has died honorably.'))
        self.the_baby.dishonorable_death_signal.connect(
            lambda: self.msg(f'{name} died dishonorably.'))

        self.the_baby.cam_status_signal.connect(
            lambda s: self.live_od_server.on_cam_ready() if s == 2 else None,
            Qt.ConnectionType.DirectConnection,
        )
        self.data_handler.done_writing_signal.connect(
            self.live_od_server.on_data_handler_done,
            Qt.ConnectionType.DirectConnection,
        )
        # For Basler cameras: notify the server when this baby's grab loop has
        # fully exited so that WAIT_CAM_READY for the next run is not released
        # prematurely (while the old RetrieveResult() call is still blocking).
        if "basler" in camera_key:
            self.the_baby.done_signal.connect(
                self.live_od_server.on_basler_baby_done,
                Qt.ConnectionType.DirectConnection,
            )

        # Clear the nanny's interrupt flag before starting the new baby.
        # Without this, if spawn_baby fires during reset()'s processEvents() loop
        # (i.e. the experiment sends INIT_RUN before the old grab loop has died),
        # persistent_get_camera() would hit break_check() → True and return a
        # DummyCamera, causing "Camera not ready" on every subsequent run.
        self.camera_nanny.interrupted = False
        self.the_baby.start()
        self.msg(f"Baby {name} born — camera_key={camera_key}")

    def on_run_done(self):
        """Called when the LiveODServer processes an END_RUN message."""
        self._run_active = False
        name = getattr(self, '_run_name', '?')
        if self.the_baby is None and not getattr(self, '_run_capture_images', True):
            # No-camera run — emit the honorable death message here.
            # (camera runs that were reset also have the_baby=None by this
            # point, so we guard with _run_capture_images to avoid printing
            # a spurious honorable-death after an aborted camera run.)
            if not self._run_was_reset:
                self.msg(f"{name} has died honorably.")
        # Camera runs emit their own honorable_death_signal message.
        self.the_baby = None
        self.data_handler = None
        # run_id is claimed + incremented atomically at INIT_RUN
        # (server_talk.claim_run_id), so there is nothing to increment here.
        self._run_was_reset = False
        self.eta_label.setText("ETA --:--")

    def on_shot_timing(self, delta_t: float, eta_str: str):
        """Update the ETA label."""
        self.eta_label.setText(f"ETA {eta_str}")

    def on_shot_progress(self, shot_idx: int, N_total: int, xvar_values: object):
        """Update the GUI with per-shot progress from the ZMQ server."""
        try:
            self.update_image_count(shot_idx + 1, N_total)
        except Exception:
            pass

    def restart_mother(self):
        """Legacy slot kept for compatibility — no-op in ZMQ mode."""
        pass

    def check_new_camera(self, camera_select):
        # Update button color immediately when camera connection changes
        if hasattr(self, 'camera_conn_bar'):
            for btn in [self.camera_conn_bar.xy_basler_button,
                        self.camera_conn_bar.basler_2dmot_button,
                        self.camera_conn_bar.x_basler_button,
                        self.camera_conn_bar.z_basler_button,
                        self.camera_conn_bar.andor]:
                if hasattr(btn, 'camera_name') and btn.camera_name == camera_select:
                    btn._set_color_success()
                elif hasattr(btn, 'camera') and btn.camera is not None and not btn.camera.is_opened():
                    btn._set_color_closed()
        if self.last_camera != camera_select:
            self.clear_plots()
            self.last_camera = camera_select
            self.set_default_roi(camera_select)

    def set_default_roi(self, camera_select):
        if 'andor' in camera_select:
            key = 'andor_all'
        elif 'basler' in camera_select:
            key = 'basler_all'
        else:
            key = None
        if key:
            self.analyzer.roi = ROI(roi_id=key, use_saved_roi=False, printouts=False)

    def get_img_number(self, N_img, N_shots, N_pwa_per_shot):
        self.N_pwa_per_shot = N_pwa_per_shot

    def count_images(self):
        self.img_count += 1
        self.img_count_run += 1
        if self.img_count == self.N_pwa_per_shot:
            self.img_count = 0

    def reset_count(self):
        self.img_count = 0
        self.img_count_run = 0
        self.analyzer.imgs = []

    def msg(self, msg):
        print(msg)
        self.output_window.appendPlainText(msg)
        if hasattr(self, 'broadcaster'):
            self.broadcaster.broadcast_log_msg(msg)

    def grab_start_msg(self, Nimg, *_):
        self.N_img = Nimg
        msg = f"Camera grabbing... Expecting {Nimg} images."
        self.msg(msg)

    def gotem_msg(self, count):
        msg = f"gotem (img {count}/{self.N_img})"
        self.msg(msg)

    def clear_plots(self):
        self.viewer_window.clear_plots()

    def update_image_count(self, count, total):
        self.viewer_window.update_image_count(count, total)

    def reset(self):
        # Guard against duplicate calls (e.g. local button + remote reset_signal
        # arriving close together).  If _reset_requested is already set and
        # there is no active run or camera baby, the reset was already handled.
        if (hasattr(self, 'live_od_server') and
                self.live_od_server._reset_requested and
                not getattr(self, '_run_active', False) and
                getattr(self, 'the_baby', None) is None):
            return
        # Ensure the ZMQ server flag is set regardless of whether this was
        # triggered by the local button or by the remote viewer (which goes
        # through _handle_reset first, but this is idempotent).
        if hasattr(self, 'live_od_server'):
            self.live_od_server._reset_requested = True
        if hasattr(self, 'camera_nanny'):
            try:
                self.camera_nanny.interrupted = True
            except Exception as e:
                print(e)
        
        if hasattr(self, 'data_handler') and self.data_handler is not None:
            try:
                self.data_handler.interrupted = True
            except Exception as e:
                print(e)
                
        if hasattr(self, 'the_baby') and self.the_baby is not None:
            try:
                self.the_baby.interrupted = True
                # self.the_baby.dishonorable_death()
                self.msg('Acquisition aborted, run ID advanced.')
            except Exception as e:
                print(e)
        else:
            if getattr(self, '_run_active', False):
                # A no-camera run (setup_camera=False) is in progress.
                # The ZMQ poll mechanism will abort it at the next shot boundary.
                # The run_id was already claimed + incremented at INIT_RUN, so
                # do not increment again here.
                name = getattr(self, '_run_name', '?')
                msg = f'Run reset. {name} has died dishonorably.'
                self._run_active = False
                self._run_was_reset = True
            else:
                # No run was ever started for this id -> manually skip it.
                msg = 'No active run. Incrementing Run ID.'
                self.server_talk.update_run_id()
            self.msg(msg)

        if self.the_baby is not None:
            baby_to_wait_for = self.the_baby
            while not getattr(baby_to_wait_for, 'dead', False):
                if self.the_baby is not baby_to_wait_for:
                    # spawn_baby() fired during processEvents() — the experiment
                    # sent INIT_RUN before the old grab loop finished dying.
                    # The old baby will finish in the background; the new one
                    # already started.  Stop waiting here so camera_nanny.
                    # interrupted gets cleared below before the new baby's
                    # persistent_get_camera() runs.
                    break
                QApplication.processEvents()
                time.sleep(0.05)

        self.queue = Queue()
        # self.restart_mother()
        self.the_baby = None
        self.data_handler = None
        self.camera_nanny.interrupted = False

if __name__ == '__main__':
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('weldlab.kexp.gui.live_od')
    app = QApplication(sys.argv)
    win = LiveODWindow()
    win.setWindowTitle("LiveOD Server")
    win.setWindowIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
    win.show()
    sys.exit(app.exec())

