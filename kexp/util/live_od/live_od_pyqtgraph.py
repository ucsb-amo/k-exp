import sys
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QDoubleSpinBox, QPlainTextEdit, QComboBox
)
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from queue import Queue
import pyqtgraph as pg
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from matplotlib import cm
from matplotlib.colors import Normalize
import os
import pickle
import json

from kexp.util.live_od.camera_mother import CameraMother, CameraBaby, DataHandler, CameraNanny
from kexp.util.live_od.camera_connection_widget import CamConnBar, ROISelector
from kexp.analysis.roi import ROI
from kexp.analysis.image_processing import compute_OD, process_ODs
from kexp.util.increment_run_id import update_run_id

class Analyzer(QThread):
    analyzed = pyqtSignal()
    def __init__(self, plotting_queue: Queue):
        super().__init__()
        self.imgs = []
        self.plotting_queue = plotting_queue
        self.roi = []
    def get_img_number(self, N_img, N_shots, N_pwa_per_shot):
        self.N_img = N_img
        self.N_shots = N_shots
        self.N_pwa_per_shot = N_pwa_per_shot
    def get_analysis_type(self, imaging_type):
        self.imaging_type = imaging_type
    def got_img(self, img):
        self.imgs.append(np.asarray(img))
        if len(self.imgs) == (self.N_pwa_per_shot + 2):
            self.analyze()
            self.imgs = []
    def analyze(self):
        self.img_atoms = self.imgs[0]
        self.img_light = self.imgs[self.N_pwa_per_shot]
        self.img_dark = self.imgs[self.N_pwa_per_shot + 1]
        self.od_raw = compute_OD(self.img_atoms, self.img_light, self.img_dark, imaging_type=self.imaging_type)
        self.od_raw = np.array([self.od_raw])
        self.od, self.sum_od_x, self.sum_od_y = process_ODs(self.od_raw, self.roi)
        self.od_raw = self.od_raw[0]
        self.od = self.od[0]
        self.sum_od_x = self.sum_od_x[0]
        self.sum_od_y = self.sum_od_y[0]
        self.analyzed.emit()
        self.plotting_queue.put((self.img_atoms, self.img_light, self.img_dark, self.od, self.sum_od_x, self.sum_od_y))

class LiveODWindow(QWidget):
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
        if self.last_camera != camera_select:
            self.clear_plots()
            self.last_camera = camera_select
            self.set_default_roi(camera_select)

    def update_roi(self):
        roi_key = self.roi_select.crop_dropdown.currentText()
        self.analyzer.roi = ROI(roi_id=roi_key)
        # Instead of clearing, re-apply the ROI to the last images if available
        if hasattr(self, 'analyzer') and hasattr(self.analyzer, 'imgs') and self.analyzer.imgs:
            # Only re-plot if we have a full set of images for analysis
            if len(self.analyzer.imgs) == (getattr(self.analyzer, 'N_pwa_per_shot', 0) + 2):
                self.analyzer.analyze()
        elif hasattr(self, 'viewer_window') and hasattr(self.viewer_window, '_last_od'):
            # Only re-plot if we have valid OD and sumod data
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
        # Add Advance Run button (bigger, light red)
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

    def advance_run(self):
        # Interrupt the whole camera baby process and restart camera mother
        if hasattr(self, 'the_baby') and self.the_baby is not None:
            try:
                if hasattr(self, 'data_handler') and self.data_handler is not None:
                    try:
                        self.data_handler.terminate()
                    except Exception as e:
                        print(e)
                self.the_baby.terminate()
                self.the_baby.dishonorable_death()
                self.the_baby = None
                print('Acquisition aborted, run ID advanced.')
            except Exception as e:
                self.msg(f"Error sending dishonorable death signal: {e}")
        # Restart camera mother to watch for new data
        self.restart_mother()

    def clear_plots(self):
        self.viewer_window.clear_plots()
    def update_image_count(self, count, total):
        self.viewer_window.update_image_count(count, total)

class LiveODViewer(QWidget):
    STATE_PATH = os.path.expanduser('~/.live_od_last_state.pkl')
    CMAP_PATH = os.path.expanduser('~/.live_od_cmap.json')
    def __init__(self):
        super().__init__()
        self.Nimg = 0
        self._sumodx_scale = 1.0
        self._sumody_scale = 1.0
        self._first_image_received = 0
        self._first_image_minmax = {}
        self._autoscale_ready = False
        self._autoscale_buffer = []
        self._cmap_name = 'viridis'  # Default colormap is now viridis
        self.init_ui()
        self._load_last_state()
        
    def init_ui(self):
        self.reset_zoom_button = QPushButton('Reset zoom')
        self.clear_button = QPushButton('Clear')
        self.image_count_label = QLabel('Image count: 0/0')
        control_bar = QHBoxLayout()
        control_bar.addWidget(self.reset_zoom_button)
        control_bar.addWidget(self.clear_button)
        control_bar.addWidget(self.image_count_label)
        control_bar.addStretch()
        # Move message panel to the top only
        self.output_window = QPlainTextEdit()
        self.output_window.setReadOnly(True)
        self.output_window.setMinimumHeight(40)
        self.output_window.setMaximumHeight(16777215)
        self.img_atoms_view = pg.ImageView()
        self.img_light_view = pg.ImageView()
        self.img_dark_view = pg.ImageView()
        img_splitter = QSplitter(Qt.Orientation.Horizontal)
        img_splitter.addWidget(self._with_label(self.img_atoms_view, 'Atoms + Light'))
        img_splitter.addWidget(self._with_label(self.img_light_view, 'Light only'))
        img_splitter.addWidget(self._with_label(self.img_dark_view, 'Dark'))
        for v in [self.img_atoms_view, self.img_light_view, self.img_dark_view]:
            v.ui.histogram.hide(); v.ui.roiBtn.hide(); v.ui.menuBtn.hide()
            self.set_pg_colormap(v, 'viridis')  # Ensure colormap is set to viridis
        self.od_plot = pg.PlotWidget()
        self.od_plot.setLabel('left', 'OD')
        self.od_plot.setLabel('bottom', 'X')
        self.od_img_item = pg.ImageItem()
        self.od_plot.addItem(self.od_img_item)
        self.od_img_item.setZValue(-10)
        self.set_pg_colormap(self.od_img_item, 'viridis')  # Ensure OD plot colormap is viridis
        self.sumodx_panel = pg.PlotWidget()
        self.sumodx_panel.setLabel('left', '')
        self.sumodx_panel.setLabel('bottom', 'X')
        self.sumodx_panel.setMouseEnabled(x=False, y=True)  # Allow y zooming only
        self.sumodx_panel.setMenuEnabled(False)
        self.sumody_panel = pg.PlotWidget()
        self.sumody_panel.setLabel('bottom', '')
        self.sumody_panel.setLabel('left', 'Y')
        self.sumody_panel.setMouseEnabled(x=True, y=False)  # Allow x zooming only
        self.sumody_panel.setMenuEnabled(False)
        self.sumody_panel.hideAxis('right'); self.sumody_panel.hideAxis('top')
        self.sumody_panel.showGrid(x=False, y=False)
        self.od_plot.setMouseEnabled(x=True, y=True)
        self.od_plot.setMenuEnabled(True)
        self.od_plot.hideAxis('right'); self.od_plot.hideAxis('top')
        self.od_plot.showGrid(x=False, y=False)
        od_grid = QSplitter(Qt.Orientation.Horizontal)
        od_left = QSplitter(Qt.Orientation.Vertical)
        od_left.addWidget(self.od_plot)
        od_left.addWidget(self.sumodx_panel)
        od_left.setSizes([400, 120])
        od_grid.addWidget(od_left)
        od_grid.addWidget(self.sumody_panel)
        od_grid.setSizes([500, 120])
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(img_splitter)
        main_splitter.addWidget(od_grid)
        main_splitter.setSizes([300, 600])
        top_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter.addWidget(self.output_window)
        controls_container = QWidget()
        controls_layout = QVBoxLayout()
        controls_layout.addLayout(control_bar)
        controls_layout.addWidget(main_splitter)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_container.setLayout(controls_layout)
        top_splitter.addWidget(controls_container)
        top_splitter.setSizes([40, 1000])  # Make top panel (message) resizable
        layout = QVBoxLayout()
        # Layout: message panel at top, then controls, then main_splitter (no bottom panel)
        layout.addWidget(top_splitter)
        self.setLayout(layout)
        self.clear_button.clicked.connect(self.clear_plots)
        self.reset_zoom_button.clicked.connect(self.reset_zoom)
        self.od_plot.scene().sigMouseClicked.connect(self.handle_mouse_click)
        self.od_plot.getViewBox().sigRangeChanged.connect(self.sync_sumod_panels)

    def _with_label(self, imgview, label):
        container = QWidget()
        layout = QVBoxLayout()
        title = QLabel(label)
        layout.addWidget(title)
        layout.addWidget(imgview)
        container.setLayout(layout)
        return container
    def _wrap_layout(self, control_bar, main_splitter):
        container = QWidget()
        vbox = QVBoxLayout()
        vbox.addLayout(control_bar)
        vbox.addWidget(main_splitter)
        vbox.setContentsMargins(0, 0, 0, 0)
        container.setLayout(vbox)
        return container
    def set_pg_colormap(self, imgitem, cmap_name):
        import matplotlib
        lut = (matplotlib.colormaps[cmap_name](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)
        # If imgitem is a pg.ImageView, set LUT on its imageItem
        if hasattr(imgitem, 'imageItem'):
            imgitem.imageItem.setLookupTable(lut)
            imgitem.imageItem.lut = lut
        else:
            imgitem.setLookupTable(lut)
            imgitem.lut = lut
    def set_all_colormaps(self, cmap_name):
        self._cmap_name = cmap_name
        for v in [self.img_atoms_view, self.img_light_view, self.img_dark_view, self.od_img_item]:
            self.set_pg_colormap(v, cmap_name)
        self._save_cmap_setting(cmap_name)
    def clear_plots(self):
        self.img_atoms_view.clear()
        self.img_light_view.clear()
        self.img_dark_view.clear()
        self.od_img_item.clear()
        self.sumodx_panel.clear()
        self.sumody_panel.clear()
        self._last_sumodx = None
        self._last_sumody = None
        self._last_od_shape = None
        self._sumodx_scale = 1.0
        self._sumody_scale = 1.0
        self._first_image_received = 0
        self._first_image_minmax = {}
        self._autoscale_ready = False
        self._autoscale_buffer = []
    def update_image_count(self, count, total):
        self.image_count_label.setText(f'Image count: {count}/{total}')
    def get_img_number(self, N_img, N_shots, N_pwa_per_shot, run_id=None):
        self.Nimg = N_img
        if run_id is not None:
            self._current_run_id = run_id
    def _save_last_state(self, atoms=None, light=None, dark=None, od=None, sumodx=None, sumody=None):
        try:
            state = {
                'atoms': atoms if atoms is not None else getattr(self, '_last_atoms', None),
                'light': light if light is not None else getattr(self, '_last_light', None),
                'dark': dark if dark is not None else getattr(self, '_last_dark', None),
                'od': od if od is not None else getattr(self, '_last_od', None),
                'sumodx': sumodx if sumodx is not None else getattr(self, '_last_sumodx', None),
                'sumody': sumody if sumody is not None else getattr(self, '_last_sumody', None),
            }
            with open(self.STATE_PATH, 'wb') as f:
                pickle.dump(state, f)
        except Exception as e:
            pass
    def _load_last_state(self):
        try:
            if os.path.exists(self.STATE_PATH):
                with open(self.STATE_PATH, 'rb') as f:
                    state = pickle.load(f)
                if all(state.get(k) is not None for k in ['atoms', 'light', 'dark', 'od', 'sumodx', 'sumody']):
                    self.plot_images(state['atoms'], state['light'], state['dark'])
                    self.plot_od(state['od'], state['sumodx'], state['sumody'])
                    self._last_atoms = state['atoms']
                    self._last_light = state['light']
                    self._last_dark = state['dark']
                    self._last_od = state['od']
                    self._last_sumodx = state['sumodx']
                    self._last_sumody = state['sumody']
        except Exception as e:
            pass
    def plot_images(self, atoms, light, dark):
        # Buffer first three images for autoscale
        if not self._autoscale_ready:
            self._autoscale_buffer.append((atoms, light, dark))
            if len(self._autoscale_buffer) >= 1:
                a, l, d = self._autoscale_buffer[0]
                self._first_image_minmax['atoms_light'] = (float(np.min(a)), float(np.max(a)))
                self._first_image_minmax['light'] = (float(np.min(l)), float(np.max(l)))
                self._first_image_minmax['dark'] = (float(np.min(d)), float(np.max(d)))
                self._autoscale_ready = True
        atoms_min, atoms_max = self._first_image_minmax.get('atoms_light', (None, None))
        light_min, light_max = self._first_image_minmax.get('light', (None, None))
        dark_min, dark_max = self._first_image_minmax.get('dark', (None, None))
        if self._autoscale_ready:
            self.img_atoms_view.setImage(atoms.T, autoLevels=False, levels=(atoms_min, atoms_max))
            self.img_light_view.setImage(light.T, autoLevels=False, levels=(atoms_min, atoms_max))
            self.img_dark_view.setImage(dark.T, autoLevels=False, levels=(dark_min, dark_max))
        else:
            self.img_atoms_view.setImage(atoms.T, autoLevels=True)
            self.img_light_view.setImage(light.T, autoLevels=True)
            self.img_dark_view.setImage(dark.T, autoLevels=True)
        self._last_atoms = atoms
        self._last_light = light
        self._last_dark = dark
        self._save_last_state(atoms=atoms, light=light, dark=dark)
    def sync_sumod_panels(self):
        # Synchronize sumodx and sumody panels to match OD plot's visible region
        od_vb = self.od_plot.getViewBox()
        x_range, y_range = od_vb.viewRange()
        self.sumodx_panel.setXRange(*x_range, padding=0)
        self.sumody_panel.setYRange(*y_range, padding=0)
    def _plot_sumodx(self, sumodx):
        if sumodx is not None:
            self.sumodx_panel.clear()
            self.sumodx_panel.plot(sumodx, pen=pg.mkPen('w', width=2))
    def _plot_sumody(self, sumody, od_shape):
        if sumody is not None:
            y = np.linspace(0, od_shape[1] - 1, len(sumody))
            x = sumody / np.max(sumody) * od_shape[0] * 0.8 + od_shape[0] * 0.1 if np.max(sumody) > 0 else sumody
            x = (x - np.mean(x)) * self._sumody_scale + np.mean(x)
            self.sumody_panel.clear()
            self.sumody_panel.plot(x, y, pen=pg.mkPen('w', width=2))
    def reset_zoom(self):
        # Reset OD plot and sumod panels to show full ROI/image
        self.od_plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.sumodx_panel.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.sumody_panel.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.sync_sumod_panels()
    def handle_mouse_click(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.reset_zoom()
    def plot_od(self, od, sumodx, sumody, min_od=None, max_od=None):
        if min_od is None or max_od is None:
            min_od = float(np.min(od))
            max_od = float(np.max(od))
        self.od_img_item.setImage(od.T, autoLevels=False, levels=(min_od, max_od))
        self._last_sumodx = sumodx
        self._last_sumody = sumody
        self._last_od_shape = od.shape
        self._plot_sumodx(sumodx)
        self._plot_sumody(sumody, od.shape)
        self._last_od = od
        self._last_sumodx = sumodx
        self._last_sumody = sumody
        self._save_last_state(od=od, sumodx=sumodx, sumody=sumody)
    def handle_plot_data(self, to_plot):
        img_atoms, img_light, img_dark, od, sum_od_x, sum_od_y = to_plot
        self.plot_images(img_atoms, img_light, img_dark)
        self.plot_od(od, sum_od_x, sum_od_y)

class LiveODPlotter(QThread):
    plot_data_signal = pyqtSignal(object)
    def __init__(self, plotwindow: 'LiveODViewer', plotting_queue: Queue):
        super().__init__()
        self.plotwindow = plotwindow
        self.plotting_queue = plotting_queue
        self.plot_data_signal.connect(self.plotwindow.handle_plot_data)
    def run(self):
        while True:
            to_plot = self.plotting_queue.get()
            self.plot_data_signal.emit(to_plot)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = LiveODWindow()
    win.setWindowTitle("LiveOD")
    win.setWindowIcon(QIcon('banana-icon.png'))
    win.show()
    sys.exit(app.exec())
