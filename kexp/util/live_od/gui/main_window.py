import sys
from queue import Queue
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
from PyQt6.QtGui import QFont, QIcon, QGuiApplication
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
from kexp.util.live_od.camera_mother import CameraMother, CameraBaby, DataHandler, CameraNanny
from kexp.util.live_od.camera_connection_widget import CamConnBar, ROISelector
from kexp.util.live_od.gui.viewer import LiveODViewer
from kexp.util.live_od.gui.analyzer import Analyzer
from kexp.util.live_od.gui.plotter import LiveODPlotter
from kexp.analysis.roi import ROI
from kexp.util.increment_run_id import update_run_id, RUN_ID_PATH
from kexp.analysis.image_processing import compute_OD, process_ODs
import numpy as np
import os
import time

class StatusLightsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.lights = {}
        layout = QVBoxLayout()
        for label in ["baby born", "cam ready", "ready marked", "ready ack"]:
            h = QHBoxLayout()
            light = QFrame()
            light.setFixedSize(18, 18)
            light.setStyleSheet("background-color: gray; border-radius: 9px; border: 1px solid black;")
            self.lights[label] = light
            h.addWidget(light)
            h.addWidget(QLabel(label))
            h.addStretch()
            layout.addLayout(h)
        self.setLayout(layout)

    def set_light(self, label, state):
        color = {True: "green", False: "gray"}[state]
        if label in self.lights:
            self.lights[label].setStyleSheet(f"background-color: {color}; border-radius: 9px; border: 1px solid black;")

    # Add methods to set the lights from signals
    def set_cam_status_lights(self,status_int):
        if status_int == -1:
            self.set_light("baby born", False)
            self.set_light("cam ready", False)
            self.set_light("ready marked", False)
            self.set_light("ready ack", False)
        elif status_int == 0:
            self.set_light("baby born", True)
        elif status_int == 1:
            self.set_light("cam ready", True)
        elif status_int == 2:
            self.set_light("ready marked", True)
        elif status_int == 3:
            self.set_light("ready ack", True)

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

    def update_run_id_label(self):
        try:
            with open(RUN_ID_PATH, 'r') as f:
                rid = f.read().strip()
            self.run_id_label.setText(f"Run ID: {rid}")
        except Exception as e:
            self.run_id_label.setText("Run ID: (unavailable)")

    def setup_widgets(self):
        self.viewer_window = LiveODViewer()
        self.setup_run_id_label()
        self.setup_output_window()
        self.setup_fix_button()
        self.camera_conn_bar = CamConnBar(self.camera_nanny, self.output_window)

        self.setup_screenshot_button()
        self.roi_select = ROISelector()
        self.roi_select.crop_dropdown.currentIndexChanged.connect(self.update_roi)
        self.plotting_queue = Queue()
        self.analyzer = Analyzer(self.plotting_queue, self.viewer_window)
        self.plotter = LiveODPlotter(self.viewer_window, self.plotting_queue)
        self.status_lights = StatusLightsWidget()
        self.plotter.start()

    def setup_screenshot_button(self):
        self.screenshot_button = QPushButton("📷 Screenshot 📷")
        self.screenshot_button.setStyleSheet('background-color: #3464eb; font-size: 16px; color: #f2f2f2; font-weight: bold;')
        self.screenshot_button.clicked.connect(self.copy_screenshot_to_clipboard)
        self.screenshot_button.clicked.connect(lambda: self.msg("Screenshot copied to clipboard."))

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
        # Add the Run ID label above the camera buttons
        # layout.addWidget(self.run_id_label)
        control_bar = QHBoxLayout()
        cam_bar = QVBoxLayout()
        cam_bar.addWidget(self.run_id_label)
        cam_bar.addWidget(self.screenshot_button) 
        cam_bar.addWidget(self.camera_conn_bar)
        control_bar.addLayout(cam_bar)
        control_bar.addWidget(self.status_lights)
        control_bar.addWidget(self.roi_select)
        control_bar.addWidget(self.fix_button)
        # control_bar.addStretch()
        layout.addLayout(control_bar)
        layout.addWidget(self.viewer_window)
        self.setLayout(layout)
    
    # Slot to copy screenshot
    def copy_screenshot_to_clipboard(self):
        # Grab the window as a QPixmap
        pixmap = self.grab()  # If this is your main window
        # Copy to clipboard
        clipboard = QGuiApplication.clipboard()
        clipboard.setPixmap(pixmap)

    def create_camera_baby(self, file, name):
        self.data_handler = DataHandler(self.queue, data_filepath=file)
        self.the_baby = CameraBaby(self.data_handler, name, self.queue, self.camera_nanny)
        self.data_handler.save_data_bool_signal.connect(self.data_handler.get_save_data_bool)
        self.data_handler.image_type_signal.connect(self.analyzer.get_analysis_type)
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

        self.the_baby.honorable_death_signal.connect(lambda: self.msg(f'Run complete. {name} has died honorably.'))

        self.the_baby.dishonorable_death_signal.connect(lambda: self.msg(f'{name} has died dishonorably. Incomplete data deleted.'))
        
        self.the_baby.done_signal.connect(self.restart_mother)
        self.the_baby.done_signal.connect(update_run_id)

        self.the_baby.cam_status_signal.connect(self.status_lights.set_cam_status_lights)
        self.the_baby.start()

    def clear_cams(self):
        self.the_baby = None
        self.data_handler = None
        
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
        self.analyzer.roi = ROI(roi_id=roi_key, use_saved_roi=False, printouts=False)
        # Recompute and replot OD from currently displayed images
        atoms = getattr(self.viewer_window, '_last_atoms', None)
        light = getattr(self.viewer_window, '_last_light', None)
        dark = getattr(self.viewer_window, '_last_dark', None)
        roi = self.analyzer.roi
        width = roi.roix[1] - roi.roix[0]
        height = roi.roiy[1] - roi.roiy[0]
        # --- Adjust OD window axis limits to match ROI aspect ratio, sized to larger axis ---
        if width > 0 and height > 0:
            if width >= height:
                x0, x1 = 0, width
                y0, y1 = 0, width * (height / width)
            else:
                y0, y1 = 0, height
                x0, x1 = 0, height * (width / height)
            self.viewer_window.od_plot.setXRange(x0, x1, padding=0)
            self.viewer_window.od_plot.setYRange(y0, y1, padding=0)
        # --- End axis adjustment ---
        if atoms is not None and light is not None and dark is not None:
            od = compute_OD(atoms, light, dark)
            od = np.array([od])
            od_cropped, sumodx, sumody = process_ODs(od, roi)
            od_cropped = od_cropped[0]
            sumodx = sumodx[0]
            sumody = sumody[0]
            self.viewer_window.plot_od(od_cropped, sumodx, sumody)
            # --- Autoscale sumodx and sumody panels ---
            if sumodx is not None and len(sumodx) > 0:
                max_x = np.max(sumodx)
                self.viewer_window.sumodx_panel.setYRange(0, max_x if max_x > 0 else 1, padding=0)
            if sumody is not None and len(sumody) > 0:
                max_y = np.max(sumody)
                self.viewer_window.sumody_panel.setYRange(0, max_y if max_y > 0 else 1, padding=0)
        elif hasattr(self, 'analyzer') and hasattr(self.analyzer, 'imgs') and self.analyzer.imgs:
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
            self.analyzer.roi = ROI(roi_id=key, use_saved_roi=False, printouts=False)
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

    def reset(self):
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
                msg = 'Acquisition aborted, run ID advanced.'
                print(msg)
                self.msg(msg)
            except Exception as e:
                print(e)
        else:
            msg = 'No active run to abort. Incrementing Run ID.'
            print(msg)
            self.msg(msg)
            update_run_id()
            pass

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
    app = QApplication(sys.argv)
    win = LiveODWindow()
    win.setWindowTitle("LiveOD")
    win.setWindowIcon(QIcon('banana-icon.png'))
    win.show()
    sys.exit(app.exec())
