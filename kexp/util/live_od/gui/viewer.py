import os
import numpy as np
import pickle
import json
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QPlainTextEdit, QSlider, QSizePolicy, QLineEdit, QDoubleSpinBox, QCheckBox
from PyQt6.QtCore import Qt
import sys
import contextlib

class SuppressPrints:
    def __init__(self, suppress=True):
        self.suppress = suppress
        self._original_stdout = None
    def __enter__(self):
        if self.suppress:
            self._original_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.suppress and self._original_stdout:
            sys.stdout.close()
            sys.stdout = self._original_stdout

class LiveODViewer(QWidget):
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
        self._od_min = 0.0
        self._od_max = 2.5
        self._od_slider_min = 0.0  # Pin minimum at zero
        self._od_slider_max = 6.0
        self._od_slider_steps = int(self._od_slider_max / 0.1) # for 0.025 step size
        self._lock_views = False  # Track lock state
        self._syncing_all_views = False  # Prevent recursion
        self.init_ui()
        
    def init_ui(self):
        self.reset_zoom_button = QPushButton('Reset zoom')
        self.clear_button = QPushButton('Clear')
        self.image_count_label = QLabel('Image count: 0/0')
        control_bar = QHBoxLayout()

        self.lock_views_checkbox = QCheckBox("Lock view ranges")
        self.lock_views_checkbox.setChecked(True)
        self.lock_views_checkbox.stateChanged.connect(self._on_lock_views_changed)

        control_bar.addWidget(self.reset_zoom_button)
        control_bar.addWidget(self.clear_button)
        control_bar.addWidget(self.lock_views_checkbox)
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
        # --- Sync zoom/pan between atom, light, and dark images ---
        self._syncing_image_views = False
        self.img_atoms_view.getView().sigRangeChanged.connect(lambda *args: self._sync_image_views(self.img_atoms_view))
        self.img_light_view.getView().sigRangeChanged.connect(lambda *args: self._sync_image_views(self.img_light_view))
        self.img_dark_view.getView().sigRangeChanged.connect(lambda *args: self._sync_image_views(self.img_dark_view))
        self.od_plot = pg.PlotWidget()
        # Set default axes limits to 0-512 for both x and y
        self.od_plot.setXRange(0, 512, padding=0)
        self.od_plot.setYRange(0, 512, padding=0)
 
        self.od_img_item = pg.ImageItem()
        self.od_plot.addItem(self.od_img_item)
        self.od_img_item.setZValue(-10)
        self.set_pg_colormap(self.od_img_item, 'viridis')
        self.sumodx_panel = pg.PlotWidget()
        self.sumodx_panel.setMouseEnabled(x=False, y=True)
        self.sumodx_panel.setMenuEnabled(False)
        self.sumody_panel = pg.PlotWidget()

        self.sumody_panel.setMouseEnabled(x=True, y=False)
        self.sumody_panel.setMenuEnabled(False)
        self.sumody_panel.hideAxis('right'); self.sumody_panel.hideAxis('top')
        self.sumody_panel.showGrid(x=False, y=False)
        
        self.od_plot.setMouseEnabled(x=True, y=True)
        self.od_plot.setMenuEnabled(True)
        self.od_plot.hideAxis('right'); self.od_plot.hideAxis('top')
        self.od_plot.showGrid(x=False, y=False)
        # --- Begin grid layout for OD and sumOD panels ---
        # Horizontal splitter: left is od_plot+sumodx (vertical), right is sumody
        od_and_sumodx_splitter = QSplitter(Qt.Orientation.Vertical)
        od_and_sumodx_splitter.addWidget(self.od_plot)
        od_and_sumodx_splitter.addWidget(self.sumodx_panel)
        self.sumodx_panel.setMinimumHeight(100)
        od_and_sumodx_splitter.setSizes([400, 120])

        od_grid = QSplitter(Qt.Orientation.Horizontal)

        sumody_splitter = QSplitter(Qt.Orientation.Vertical)
        sumody_splitter.addWidget(self.sumody_panel)
        # Add OD min/max sliders below sumody_panel
        od_controls_widget = QWidget()
        od_controls_layout = QVBoxLayout()
        od_controls_layout.setContentsMargins(5, 5, 5, 5)
        od_controls_layout.setSpacing(5)

        # --- Min OD slider with value labels ---
        min_slider_layout = QVBoxLayout()
        min_slider_label_row = QHBoxLayout()
        min_slider_row = QHBoxLayout()
        min_label = QLabel('Min OD:')
        min_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.od_min_spinner = QDoubleSpinBox()
        self.od_min_spinner.setDecimals(1)
        self.od_min_spinner.setSingleStep(0.1)
        self.od_min_spinner.setRange(self._od_slider_min, self._od_slider_max)
        self.od_min_spinner.setValue(self._od_min)
        self.od_min_spinner.setMaximumWidth(70)
        self.od_min_spinner.valueChanged.connect(self._on_od_min_spinner_changed)
        min_left_label = QLabel(f"{self._od_slider_min:.1f}")
        min_left_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.od_min_slider = QSlider(Qt.Orientation.Horizontal)
        self.od_min_slider.setMinimum(0)
        self.od_min_slider.setMaximum(self._od_slider_steps)
        self.od_min_slider.setValue(int((self._od_min - self._od_slider_min) / (self._od_slider_max - self._od_slider_min) * self._od_slider_steps))
        self.od_min_slider.valueChanged.connect(self._on_od_slider_changed)
        self.od_min_slider.setStyleSheet("QSlider::handle:horizontal {height: 28px; width: 18px; border-radius: 6px; background: #0078d7; border: 2px solid #444;} QSlider {height: 24px;}")
        min_right_label = QLabel(f"{self._od_slider_max:.1f}")
        min_right_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        min_slider_label_row.addWidget(min_label)
        min_slider_label_row.addWidget(self.od_min_spinner)

        min_slider_row.addWidget(min_left_label)
        min_slider_row.addWidget(self.od_min_slider)
        min_slider_row.addWidget(min_right_label)

        min_slider_layout.addLayout(min_slider_label_row)
        min_slider_layout.addLayout(min_slider_row)

        # --- Max OD slider with value labels ---
        max_slider_layout = QVBoxLayout()
        max_slider_label_row = QHBoxLayout()
        max_slider_row = QHBoxLayout()
        max_label = QLabel('Max OD:')
        max_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.od_max_spinner = QDoubleSpinBox()
        self.od_max_spinner.setDecimals(1)
        self.od_max_spinner.setSingleStep(0.1)
        self.od_max_spinner.setRange(self._od_slider_min, self._od_slider_max)
        self.od_max_spinner.setValue(self._od_max)
        self.od_max_spinner.setMaximumWidth(70)
        self.od_max_spinner.valueChanged.connect(self._on_od_max_spinner_changed)
        max_left_label = QLabel(f"{self._od_slider_min:.1f}")
        max_left_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.od_max_slider = QSlider(Qt.Orientation.Horizontal)
        self.od_max_slider.setMinimum(0)
        self.od_max_slider.setMaximum(self._od_slider_steps)
        self.od_max_slider.setValue(int((self._od_max - self._od_slider_min) / (self._od_slider_max - self._od_slider_min) * self._od_slider_steps))
        self.od_max_slider.valueChanged.connect(self._on_od_slider_changed)
        self.od_max_slider.setStyleSheet("QSlider::handle:horizontal {height: 28px; width: 18px; border-radius: 6px; background: #0078d7; border: 2px solid #444;} QSlider {height: 24px;}")
        max_right_label = QLabel(f"{self._od_slider_max:.1f}")
        max_right_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        max_slider_label_row.addWidget(max_label)
        max_slider_label_row.addWidget(self.od_max_spinner)

        max_slider_row.addWidget(max_left_label)
        max_slider_row.addWidget(self.od_max_slider)
        max_slider_row.addWidget(max_right_label)

        max_slider_layout.addLayout(max_slider_label_row)
        max_slider_layout.addLayout(max_slider_row)

        # --- Add to controls layout ---
        od_controls_layout.addLayout(min_slider_layout)
        od_controls_layout.addLayout(max_slider_layout)
        od_controls_widget.setLayout(od_controls_layout)
        sumody_splitter.addWidget(od_controls_widget)
        sumody_splitter.setSizes([400, 80])

        # Synchronize vertical split positions
        def sync_vertical_splitter(pos):
            sumody_splitter.setSizes(pos)
        def sync_vertical_splitter_reverse(pos):
            od_and_sumodx_splitter.setSizes(pos)
        od_and_sumodx_splitter.splitterMoved.connect(
            lambda pos, index: sync_vertical_splitter(od_and_sumodx_splitter.sizes()))
        sumody_splitter.splitterMoved.connect(
            lambda pos, index: sync_vertical_splitter_reverse(sumody_splitter.sizes()))

        od_grid.addWidget(od_and_sumodx_splitter)
        od_grid.addWidget(sumody_splitter)
        od_grid.addWidget(sumody_splitter)
        
        od_grid.setSizes([500, 120])
        # --- End grid layout ---
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
        self.od_plot.getViewBox().sigRangeChanged.connect(self.sync_sumod_panels)

        # Connect all view range signals
        self.img_atoms_view.getView().sigRangeChanged.connect(lambda *args: self._on_any_view_range_changed('atoms'))
        self.img_light_view.getView().sigRangeChanged.connect(lambda *args: self._on_any_view_range_changed('light'))
        self.img_dark_view.getView().sigRangeChanged.connect(lambda *args: self._on_any_view_range_changed('dark'))
        self.od_plot.getViewBox().sigRangeChanged.connect(lambda *args: self._on_any_view_range_changed('od'))
        
        self._on_lock_views_changed(True)

        self.sync_sumod_panels()
        sync_vertical_splitter(od_and_sumodx_splitter.sizes())
        sync_vertical_splitter_reverse(sumody_splitter.sizes())

    def _on_lock_views_changed(self, state):
        self._lock_views = bool(state)
        if self._lock_views:
            # When locking, immediately sync all to the current atoms view
            ref_range = self.img_atoms_view.getView().viewRange()
            self._sync_all_views(ref_range)

    def _on_any_view_range_changed(self, source):
        if not self._lock_views or self._syncing_all_views:
            return
        # Get the new range from the source
        if source == 'atoms':
            ref_range = self.img_atoms_view.getView().viewRange()
        elif source == 'light':
            ref_range = self.img_light_view.getView().viewRange()
        elif source == 'dark':
            ref_range = self.img_dark_view.getView().viewRange()
        elif source == 'od':
            ref_range = self.od_plot.getViewBox().viewRange()
        else:
            return
        self._sync_all_views(ref_range, exclude=source)

    def _sync_all_views(self, ref_range, exclude=None):
        self._syncing_all_views = True
        # ref_range: [xRange, yRange]
        if exclude != 'atoms':
            self.img_atoms_view.getView().setRange(xRange=ref_range[0], yRange=ref_range[1], padding=0)
        if exclude != 'light':
            self.img_light_view.getView().setRange(xRange=ref_range[0], yRange=ref_range[1], padding=0)
        if exclude != 'dark':
            self.img_dark_view.getView().setRange(xRange=ref_range[0], yRange=ref_range[1], padding=0)
        if exclude != 'od':
            self.od_plot.getViewBox().setRange(xRange=ref_range[0], yRange=ref_range[1], padding=0)
        self._syncing_all_views = False

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
        self._roi_set_count = 0
        self._first_image_received = 0
        if hasattr(self, '_last_view_ranges'):
            del self._last_view_ranges

    def update_image_count(self, count, total):
        self.image_count_label.setText(f'Image count: {count}/{total}')

    def get_img_number(self, N_img, N_shots, N_pwa_per_shot, run_id=None):
        self.Nimg = N_img
        if run_id is not None:
            self._current_run_id = run_id

    def plot_images(self, atoms, light, dark):
        # Determine if this is the first image after a clear
        is_first = not hasattr(self, '_last_view_ranges') or self._first_image_received == 0

        # Save current view ranges (for subsequent calls)
        atoms_range = self.img_atoms_view.getView().viewRange()
        light_range = self.img_light_view.getView().viewRange()
        dark_range = self.img_dark_view.getView().viewRange()
        self._last_view_ranges = {
            'atoms': atoms_range,
            'light': light_range,
            'dark': dark_range
        }

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

        # Set view range
        if is_first:
            # Set to full image range
            shape = atoms.T.shape
            self.img_atoms_view.getView().setRange(xRange=[0, shape[0]], yRange=[0, shape[1]], padding=0)
            self.img_light_view.getView().setRange(xRange=[0, shape[0]], yRange=[0, shape[1]], padding=0)
            self.img_dark_view.getView().setRange(xRange=[0, shape[0]], yRange=[0, shape[1]], padding=0)
            self._first_image_received = 1
        else:
            # Restore previous view ranges
            self.img_atoms_view.getView().setRange(xRange=self._last_view_ranges['atoms'][0], yRange=self._last_view_ranges['atoms'][1], padding=0)
            self.img_light_view.getView().setRange(xRange=self._last_view_ranges['light'][0], yRange=self._last_view_ranges['light'][1], padding=0)
            self.img_dark_view.getView().setRange(xRange=self._last_view_ranges['dark'][0], yRange=self._last_view_ranges['dark'][1], padding=0)

    def sync_sumod_panels(self):
        od_vb = self.od_plot.getViewBox()
        x_range, y_range = od_vb.viewRange()

        self.od_plot.setYRange(*y_range, padding=0)
        self.od_plot.setXRange(*x_range, padding=0)

        # Recompute sumodx and sumody for cropped region if OD data exists
        if hasattr(self, '_last_od') and self._last_od is not None:
            od = self._last_od
            # Crop indices
            x0 = max(int(np.floor(x_range[0])), 0)
            x1 = min(int(np.ceil(x_range[1])), od.shape[1])
            y0 = max(int(np.floor(y_range[0])), 0)
            y1 = min(int(np.ceil(y_range[1])), od.shape[0])
            # Crop and sum
            cropped = od[y0:y1, x0:x1]
            sumodx = np.sum(cropped, axis=0) if cropped.size > 0 else np.zeros(x1 - x0)
            sumody = np.sum(cropped, axis=1) if cropped.size > 0 else np.zeros(y1 - y0)
            self._plot_sumodx(sumodx)
            self._plot_sumody(sumody, cropped.shape)

        # self.sumodx_panel.setXRange(*x_range, padding=0)
        # self.sumody_panel.setYRange(*y_range, padding=0)

    def _plot_sumodx(self, sumodx):
        if sumodx is not None:
            self.sumodx_panel.clear()
            self.sumodx_panel.plot(sumodx, pen=pg.mkPen('w', width=2))
            # On first shot of a run, set y axis 0 to 1.5*max

    def _plot_sumody(self, sumody, od_shape):
        if sumody is not None:
            y = np.linspace(0, od_shape[0] - 1, len(sumody))
            x = sumody / np.max(sumody) * od_shape[0] * 0.8 + od_shape[0] * 0.1 if np.max(sumody) > 0 else sumody
            x = (x - np.mean(x)) * self._sumody_scale + np.mean(x)
            self.sumody_panel.clear()
            self.sumody_panel.plot(x, y, pen=pg.mkPen('w', width=2))
            # On first shot of a run, set y axis 0 to 1.5*max

    def reset_zoom(self):
        # Reset OD plot axes to original default limits
        self.od_plot.setXRange(0, 512, padding=0)
        self.od_plot.setYRange(0, 512, padding=0)
        self.sumodx_panel.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.sumody_panel.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.sync_sumod_panels()

    # def handle_mouse_click(self, event):
    #     if event.button() == Qt.MouseButton.RightButton:
    #         self.reset_zoom()

    def _on_od_range_changed(self):
        self._od_min = self.od_min_slider.value()
        self._od_max = self.od_max_slider.value()
        # Re-plot OD with new min/max if OD data exists
        if hasattr(self, '_last_od') and self._last_od is not None:
            self.plot_od(self._last_od, self._last_sumodx, self._last_sumody, min_od=self._od_min, max_od=self._od_max)

    def _on_od_slider_changed(self):
        min_val = self.od_min_slider.value() / self._od_slider_steps * (self._od_slider_max - self._od_slider_min) + self._od_slider_min
        max_val = self.od_max_slider.value() / self._od_slider_steps * (self._od_slider_max - self._od_slider_min) + self._od_slider_min
        # Prevent min > max
        if min_val > max_val:
            if self.sender() == self.od_min_slider:
                self.od_max_slider.setValue(self.od_min_slider.value())
                max_val = min_val
            else:
                self.od_min_slider.setValue(self.od_max_slider.value())
                min_val = max_val
        self._od_min = min_val
        self._od_max = max_val
        self.od_min_spinner.blockSignals(True)
        self.od_max_spinner.blockSignals(True)
        self.od_min_spinner.setValue(self._od_min)
        self.od_max_spinner.setValue(self._od_max)
        self.od_min_spinner.blockSignals(False)
        self.od_max_spinner.blockSignals(False)
        if hasattr(self, '_last_od') and self._last_od is not None:
            self.plot_od(self._last_od, self._last_sumodx, self._last_sumody, min_od=self._od_min, max_od=self._od_max)

    def _on_od_min_spinner_changed(self, val):
        val = max(self._od_slider_min, min(val, self._od_max))
        slider_val = int((val - self._od_slider_min) / (self._od_slider_max - self._od_slider_min) * self._od_slider_steps)
        self.od_min_slider.blockSignals(True)
        self.od_min_slider.setValue(slider_val)
        self.od_min_slider.blockSignals(False)
        self._od_min = val
        if hasattr(self, '_last_od') and self._last_od is not None:
            self.plot_od(self._last_od, self._last_sumodx, self._last_sumody, min_od=self._od_min, max_od=self._od_max)

    def _on_od_max_spinner_changed(self, val):
        val = min(self._od_slider_max, max(val, self._od_min))
        slider_val = int((val - self._od_slider_min) / (self._od_slider_max - self._od_slider_min) * self._od_slider_steps)
        self.od_max_slider.blockSignals(True)
        self.od_max_slider.setValue(slider_val)
        self.od_max_slider.blockSignals(False)
        self._od_max = val
        if hasattr(self, '_last_od') and self._last_od is not None:
            self.plot_od(self._last_od, self._last_sumodx, self._last_sumody, min_od=self._od_min, max_od=self._od_max)

    def plot_od(self, od, sumodx, sumody, min_od=None, max_od=None):
        # If this is the first OD after a clear, set axes to match its shape
        if getattr(self, '_last_od_shape', None) is None and od is not None:
            self.od_plot.setXRange(0, od.shape[1], padding=0)
            self.od_plot.setYRange(0, od.shape[0], padding=0)
        if min_od is None or max_od is None:
            min_od = self._od_min
            max_od = self._od_max
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
        self._syncing_image_views = True # workaround for not having image sizes reset on replotting new images
        self.plot_images(img_atoms, img_light, img_dark)
        self._syncing_image_views = False
        self.plot_od(od, sum_od_x, sum_od_y)

    def _sync_image_views(self, source_view):
        if self._syncing_image_views:
            return
        self._syncing_image_views = True
        target_views = [self.img_atoms_view, self.img_light_view, self.img_dark_view]
        src_range = source_view.getView().viewRange()
        for v in target_views:
            if v is not source_view:
                v.getView().setRange(xRange=src_range[0], yRange=src_range[1], padding=0)
        self._syncing_image_views = False

    def get_od_view_range(self):
        """
        Get the current view range of the OD plot
        
        Returns:
            tuple: (x_range, y_range) where each range is [min, max]
        """
        try:
            od_vb = self.od_plot.getViewBox()
            x_range, y_range = od_vb.viewRange()
            return x_range, y_range
        except Exception as e:
            # Return default range if anything goes wrong
            return [0, 512], [0, 512]
