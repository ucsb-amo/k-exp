import os
import numpy as np
import pickle
import json
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QPlainTextEdit
from PyQt6.QtCore import Qt

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
        
    def init_ui(self):
        self.reset_zoom_button = QPushButton('Reset zoom')
        self.clear_button = QPushButton('Clear')
        self.image_count_label = QLabel('Image count: 0/0')
        control_bar = QHBoxLayout()
        control_bar.addWidget(self.reset_zoom_button)
        control_bar.addWidget(self.clear_button)
        control_bar.addWidget(self.image_count_label)
        control_bar.addStretch()
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
            self.set_pg_colormap(v, 'viridis')
        self.od_plot = pg.PlotWidget()
        self.od_plot.setLabel('left', 'OD')
        self.od_plot.setLabel('bottom', 'X')
        self.od_img_item = pg.ImageItem()
        self.od_plot.addItem(self.od_img_item)
        self.od_img_item.setZValue(-10)
        self.set_pg_colormap(self.od_img_item, 'viridis')
        self.sumodx_panel = pg.PlotWidget()
        self.sumodx_panel.setLabel('left', '')
        self.sumodx_panel.setLabel('bottom', 'X')
        self.sumodx_panel.setMouseEnabled(x=False, y=True)
        self.sumodx_panel.setMenuEnabled(False)
        self.sumody_panel = pg.PlotWidget()
        self.sumody_panel.setLabel('bottom', '')
        self.sumody_panel.setLabel('left', 'Y')
        self.sumody_panel.setMouseEnabled(x=True, y=False)
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
        top_splitter.setSizes([40, 1000])
        layout = QVBoxLayout()
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
    def set_pg_colormap(self, imgitem, cmap_name):
        import matplotlib
        lut = (matplotlib.colormaps[cmap_name](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)
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
    def plot_images(self, atoms, light, dark):
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
    def sync_sumod_panels(self):
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
    def handle_plot_data(self, to_plot):
        img_atoms, img_light, img_dark, od, sum_od_x, sum_od_y = to_plot
        self.plot_images(img_atoms, img_light, img_dark)
        self.plot_od(od, sum_od_x, sum_od_y)
