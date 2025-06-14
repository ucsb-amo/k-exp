import sys
from queue import Queue
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, pyqtSignal
from kexp.util.live_od.camera_mother import CameraMother, CameraBaby, DataHandler, CameraNanny
from kexp.util.live_od.camera_connection_widget import CamConnBar, ROISelector
from kexp.util.live_od.gui.viewer import LiveODViewer
from kexp.util.live_od.gui.analyzer import Analyzer
from kexp.util.live_od.gui.plotter import LiveODPlotter
from kexp.analysis.roi import ROI
from kexp.util.increment_run_id import update_run_id

class LiveODWindow(QWidget):
    interrupt = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        self.camera_nanny = CameraNanny()
        self.camera_mother = CameraMother(start_watching=False, manage_babies=False, output_queue=self.queue, camera_nanny=self.camera_nanny, N_runs=1)
        self.last_camera = ""
        self.img_count = 0
        self.img_count_run = 0
        self.setup_widgets()
        self.setup_layout()
        self.camera_mother.new_camera_baby.connect(self.create_camera_baby)
        self.camera_mother.start()

    def setup_widgets(self):
        font = QFont()
        font.setPointSize(10)
        self.viewer_window = LiveODViewer()
        self.output_window = self.viewer_window.output_window
        self.output_window.setFont(font)
        self.output_window.setReadOnly(True)
        self.camera_conn_bar = CamConnBar(self.camera_nanny, self.output_window)
        self.roi_select = ROISelector()
        self.roi_select.crop_dropdown.currentIndexChanged.connect(self.update_roi)
        self.plotting_queue = Queue()
        self.analyzer = Analyzer(self.plotting_queue)
        self.analyzer.analyzed.connect(lambda: self.msg('new OD!'))
        self.plotter = LiveODPlotter(self.viewer_window, self.plotting_queue)
        self.plotter.start()
        self.advance_run_button = QPushButton('Fix')
        self.advance_run_button.setMinimumHeight(40)
        self.advance_run_button.setStyleSheet('background-color: #ffcccc; font-size: 18px; font-weight: bold;')
        self.advance_run_button.clicked.connect(self.advance_run)

    def setup_layout(self):
        layout = QVBoxLayout()
        control_bar = QHBoxLayout()
        control_bar.addWidget(self.camera_conn_bar)
        control_bar.addWidget(self.roi_select)
        control_bar.addWidget(self.advance_run_button)
        control_bar.addStretch()
        layout.addLayout(control_bar)
        layout.addWidget(self.viewer_window)
        self.setLayout(layout)

    def create_camera_baby(self, file, name):
        self.the_baby = CameraBaby(file, name, self.queue, self.camera_nanny)
        self.data_handler = DataHandler(self.queue, data_filepath=file)
        self.the_baby.save_data_bool_signal.connect(self.data_handler.get_save_data_bool)
        self.the_baby.camera_connect.connect(self.check_new_camera)
        self.the_baby.camera_grab_start.connect(self.grab_start_msg)
        self.the_baby.camera_grab_start.connect(self.get_img_number)
        self.the_baby.camera_grab_start.connect(self.data_handler.get_img_number)
        self.the_baby.camera_grab_start.connect(self.viewer_window.get_img_number)
        self.the_baby.camera_grab_start.connect(self.analyzer.get_img_number)
        self.the_baby.image_type_signal.connect(self.analyzer.get_analysis_type)
        self.the_baby.camera_grab_start.connect(self.data_handler.start)
        self.the_baby.camera_grab_start.connect(self.reset_count)
        self.data_handler.got_image_from_queue.connect(self.analyzer.got_img)
        self.data_handler.got_image_from_queue.connect(self.count_images)
        self.the_baby.honorable_death_signal.connect(lambda: self.msg(f'Run complete. {name} has died honorably.'))
        self.the_baby.dishonorable_death_signal.connect(lambda: self.msg(f'{name} has died dishonorably. Incomplete data deleted.'))
        self.the_baby.honorable_death_signal.connect(self.restart_mother)
        self.the_baby.dishonorable_death_signal.connect(self.restart_mother)
        self.the_baby.start()

    def restart_mother(self):
        import time
        time.sleep(0.25)
        self.camera_mother.start()

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
                elif hasattr(btn, 'camera') and not btn.camera.is_opened():
                    btn._set_color_closed()
        if self.last_camera != camera_select:
            self.clear_plots()
            self.last_camera = camera_select
            self.set_default_roi(camera_select)

    def update_roi(self):
        roi_key = self.roi_select.crop_dropdown.currentText()
        self.analyzer.roi = ROI(roi_id=roi_key)
        if hasattr(self, 'analyzer') and hasattr(self.analyzer, 'imgs') and self.analyzer.imgs:
            if len(self.analyzer.imgs) == (getattr(self.analyzer, 'N_pwa_per_shot', 0) + 2):
                self.analyzer.analyze()
        elif hasattr(self, 'viewer_window') and hasattr(self.viewer_window, '_last_od'):
            od = getattr(self.viewer_window, '_last_od', None)
            sumodx = getattr(self.viewer_window, '_last_sumodx', None)
            sumody = getattr(self.viewer_window, '_last_sumody', None)
            if od is not None and sumodx is not None and sumody is not None:
                self.viewer_window.plot_od(od, sumodx, sumody)

    def set_default_roi(self, camera_select):
        if 'andor' in camera_select:
            key = 'andor_all'
        elif 'basler' in camera_select:
            key = 'basler_all'
        else:
            key = None
        if key:
            self.analyzer.roi = ROI(roi_id=key, use_saved_roi=False)
            self.roi_select.set_dropdown_to_key(key)

    def get_img_number(self, N_img, N_shots, N_pwa_per_shot):
        self.N_pwa_per_shot = N_pwa_per_shot

    def count_images(self):
        self.img_count += 1
        self.img_count_run += 1
        self.update_image_count(self.img_count_run, self.N_img if hasattr(self, 'N_img') else 0)
        if self.img_count == self.N_pwa_per_shot:
            self.img_count = 0

    def reset_count(self):
        self.img_count = 0
        self.img_count_run = 0
        self.analyzer.imgs = []

    def msg(self, msg):
        self.output_window.appendPlainText(msg)

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
    def advance_run(self):
        if hasattr(self, 'the_baby') and self.the_baby is not None:
            try:
                if hasattr(self, 'data_handler') and self.data_handler is not None:
                    try:
                        if hasattr(self.data_handler, 'stop') and callable(self.data_handler.stop):
                            self.data_handler.stop()
                        else:
                            if hasattr(self.data_handler, 'file') and self.data_handler.file is not None:
                                try:
                                    self.data_handler.file.close()
                                except Exception:
                                    pass
                            self.data_handler.terminate()
                    except Exception as e:
                        print(e)
                    self.data_handler = None
                if hasattr(self.the_baby, 'stop') and callable(self.the_baby.stop):
                    self.the_baby.stop()
                else:
                    self.the_baby.terminate()
                    self.the_baby.dishonorable_death()
                self.the_baby = None
                self.queue = Queue()
                print('Acquisition aborted, run ID advanced.')
            except Exception as e:
                self.msg(f"Error sending dishonorable death signal: {e}")
        update_run_id()
        self.restart_mother()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = LiveODWindow()
    win.setWindowTitle("LiveOD")
    win.setWindowIcon(QIcon('banana-icon.png'))
    win.show()
    sys.exit(app.exec())
