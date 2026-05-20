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
        self.live_od_server.run_done_signal.connect(self.on_run_done)
        self.live_od_server.reset_signal.connect(self.reset)
        self.live_od_server.start()

        # ZMQ PUB broadcaster — forwards OD images and run events to remote viewers.
        self.broadcaster = LiveODBroadcaster()
        self.broadcaster.start()
        self.live_od_server.run_started_signal.connect(self.broadcaster.broadcast_run_started)
        self.live_od_server.shot_progress_signal.connect(self.broadcaster.broadcast_shot_progress)
        self.live_od_server.run_done_signal.connect(self.broadcaster.broadcast_run_done)
        self.analyzer.broadcast_signal.connect(self.broadcaster.broadcast_od_image)

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
        self.setup_output_window()
        self.setup_fix_button()
        self.camera_conn_bar = CamConnBar(self.camera_nanny, self.output_window)

        self.plotting_queue = Queue()
        self.analyzer = Analyzer(self.plotting_queue, self.viewer_window)
        self.plotter = LiveODPlotter(self.viewer_window, self.plotting_queue)
        self.plotter.start()

    def setup_screenshot_button(self):
        pass  # removed

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
        self.run_id_timer.start(1)  # 10 seconds

    def setup_layout(self):
        layout = QVBoxLayout()
        control_bar = QHBoxLayout()
        cam_bar = QVBoxLayout()
        cam_bar.addWidget(self.run_id_label)
        cam_bar.addWidget(self.camera_conn_bar)
        control_bar.addLayout(cam_bar)
        control_bar.addWidget(self.fix_button)
        layout.addLayout(control_bar)
        layout.addWidget(self.viewer_window)
        self.setLayout(layout)
    
    # Slot to copy screenshot removed.

    def create_camera_baby(self, file, name):
        """Legacy stub — use spawn_baby via LiveODServer.new_run_signal."""
        self.spawn_baby(filepath=file, camera_key="",
                        capture_images=True, save_data=True,
                        imaging_type=0)

    def spawn_baby(self, filepath: str, camera_key: str,
                   capture_images: bool, save_data: bool,
                   imaging_type: int, n_img: int = 1,
                   n_shots: int = 1, n_pwa: int = 1):
        """Spawn a new CameraBaby for an incoming run.

        Called from LiveODServer.new_run_signal (Qt queued connection so this
        always runs on the GUI thread).
        """
        name = names.get_first_name()
        self._run_name = name

        self._run_active = True

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

        self.data_handler = DataHandler(
            self.queue, data_filepath=filepath,
            save_data=save_data,
            imaging_type=imaging_type,
            camera_key=camera_key,
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

        self.the_baby.start()
        self.msg(f"Baby {name} born — camera_key={camera_key}")

    def on_run_done(self):
        """Called when the LiveODServer processes an END_RUN message."""
        self._run_active = False
        name = getattr(self, '_run_name', '?')
        if self.the_baby is None:
            # No-camera run — emit the honorable death message here.
            self.msg(f"{name}: All shots complete.")
            self.msg(f"{name} has died honorably.")
        # Camera runs emit their own honorable_death_signal message.
        self.the_baby = None
        self.data_handler = None

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
                self.data_handler.quit()
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
                name = getattr(self, '_run_name', '?')
                msg = f'Run reset. {name} has died dishonorably.'
                self._run_active = False
            else:
                msg = 'No active run. Incrementing Run ID.'
            self.msg(msg)
            self.server_talk.update_run_id()

        if self.the_baby is not None:
            while not getattr(self.the_baby, 'dead', False):
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

