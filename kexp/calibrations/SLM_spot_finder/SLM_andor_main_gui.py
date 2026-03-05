import sys
import time
import numpy as np
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
from artiq.language.environment import EnvExperiment

from waxx.control import AndorEMCCD, DummyCamera

from andor_group import CameraWorker, FrameBuffer, reset_camera_state, apply_camera_params
from slm_group import SLMController, SLMPreviewWidget

class LiveScanPreviewDialog(QtWidgets.QDialog):
    def __init__(self, nx, ny, xs, ys, parent=None, title="Scan Preview (live)"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 800)

        self.nx = int(nx)
        self.ny = int(ny)
        self.xs = list(xs)
        self.ys = list(ys)

        self.H = None
        self.W = None
        self.mosaic = None
        self._initialized = False
        self._levels = None
        self._grid_lines_added = False

        layout = QtWidgets.QVBoxLayout(self)
        self.pw = pg.PlotWidget()
        layout.addWidget(self.pw)

        self.pw.setMenuEnabled(False)
        self.pw.setMouseEnabled(x=True, y=True)
        self.pw.setAspectLocked(True)

        self.pw.showAxis("bottom", True)
        self.pw.showAxis("left", True)
        self.pw.showAxis("top", False)
        self.pw.showAxis("right", False)

        self.pw.setLabel("bottom", "spot center-x")
        self.pw.setLabel("left", "spot center-y")
        self.pw.invertY(True)

        self.img_item = pg.ImageItem()
        self.pw.addItem(self.img_item)

        self._msg = pg.TextItem("Waiting for first frame...", anchor=(0, 0))
        self._msg.setPos(0, 0)
        self.pw.addItem(self._msg)

    def _init_with_frame(self, frame: np.ndarray):
        self.H, self.W = frame.shape
        self.mosaic = np.zeros((self.H * self.ny, self.W * self.nx), dtype=frame.dtype)

        x_ticks = [((c + 0.5) * self.W, str(self.xs[c])) for c in range(self.nx)]
        y_ticks = [((r + 0.5) * self.H, str(self.ys[r])) for r in range(self.ny)]
        self.pw.getAxis("bottom").setTicks([x_ticks])
        self.pw.getAxis("left").setTicks([y_ticks])

        if not self._grid_lines_added:
            for c in range(1, self.nx):
                x = c * self.W
                line = pg.InfiniteLine(pos=x, angle=90, movable=False)
                line.setZValue(10)
                self.pw.addItem(line)

            for r in range(1, self.ny):
                y = r * self.H
                line = pg.InfiniteLine(pos=y, angle=0, movable=False)
                line.setZValue(10)
                self.pw.addItem(line)

            self._grid_lines_added = True

        f = frame.astype(np.float32, copy=False).ravel()
        lo = float(np.percentile(f, 1))
        hi = float(np.percentile(f, 99))
        if hi <= lo:
            lo, hi = float(np.min(f)), float(np.max(f) + 1.0)
        self._levels = (lo, hi)
        self.img_item.setLevels(self._levels)

        try:
            self.pw.removeItem(self._msg)
        except Exception:
            pass

        self.img_item.setImage(self.mosaic.T, autoLevels=False)
        self._initialized = True

    @QtCore.pyqtSlot(int, int, object)
    def update_tile(self, r: int, c: int, frame_obj):
        if frame_obj is None:
            return
        frame = frame_obj
        if not isinstance(frame, np.ndarray) or frame.ndim != 2:
            return

        if not self._initialized:
            self._init_with_frame(frame)

        if frame.shape != (self.H, self.W):
            return

        y0 = r * self.H
        y1 = (r + 1) * self.H
        x0 = c * self.W
        x1 = (c + 1) * self.W
        self.mosaic[y0:y1, x0:x1] = frame

        self.img_item.setImage(self.mosaic.T, autoLevels=False)


class FinalScanPreviewDialog(QtWidgets.QDialog):
    def __init__(self, frames_grid, xs, ys, parent=None, title="Scan Preview"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 820)

        self.xs = list(xs)
        self.ys = list(ys)

        self.ny = len(frames_grid)
        self.nx = len(frames_grid[0]) if self.ny > 0 else 0

        sample = None
        for r in range(self.ny):
            for c in range(self.nx):
                if frames_grid[r][c] is not None:
                    sample = frames_grid[r][c]
                    break
            if sample is not None:
                break

        if sample is None:
            layout = QtWidgets.QVBoxLayout(self)
            layout.addWidget(QtWidgets.QLabel("No frames captured."))
            return

        self.H, self.W = sample.shape

        self.mosaic = np.zeros((self.H * self.ny, self.W * self.nx), dtype=sample.dtype)
        for r in range(self.ny):
            for c in range(self.nx):
                fr = frames_grid[r][c]
                if fr is None:
                    continue
                self.mosaic[r * self.H:(r + 1) * self.H, c * self.W:(c + 1) * self.W] = fr

        layout = QtWidgets.QVBoxLayout(self)

        self.pw = pg.PlotWidget()
        layout.addWidget(self.pw)

        self.pw.setMenuEnabled(False)
        vb = self.pw.getViewBox()
        vb.setMouseEnabled(x=False, y=False)
        vb.setMenuEnabled(False)
        self.pw.setAspectLocked(True)

        self.pw.showAxis("bottom", True)
        self.pw.showAxis("left", True)
        self.pw.showAxis("top", False)
        self.pw.showAxis("right", False)

        self.pw.setLabel("bottom", "spot center-x")
        self.pw.setLabel("left", "spot center-y")
        self.pw.invertY(True)

        self.img_item = pg.ImageItem()
        self.pw.addItem(self.img_item)
        self.img_item.setImage(self.mosaic.T, autoLevels=True)

        x_ticks = [((c + 0.5) * self.W, str(self.xs[c])) for c in range(self.nx)]
        y_ticks = [((r + 0.5) * self.H, str(self.ys[r])) for r in range(self.ny)]
        self.pw.getAxis("bottom").setTicks([x_ticks])
        self.pw.getAxis("left").setTicks([y_ticks])

        for c in range(1, self.nx):
            self.pw.addItem(pg.InfiniteLine(pos=c * self.W, angle=90, movable=False))
        for r in range(1, self.ny):
            self.pw.addItem(pg.InfiniteLine(pos=r * self.H, angle=0, movable=False))

        self.center_readout = QtWidgets.QLabel("center=(?, ?)  (right-click to copy)")
        self.center_readout.setStyleSheet("color: gray;")
        layout.addWidget(self.center_readout)
        self._mouse_proxy = pg.SignalProxy(
            self.pw.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )

        self._last_center = None  # (xc, yc)
        self.pw.scene().sigMouseClicked.connect(self._on_mouse_clicked)

    def _pixel_to_center(self, x: int, y: int):
        if x < 0 or y < 0 or x >= self.W * self.nx or y >= self.H * self.ny:
            return None
        c = x // self.W
        r = y // self.H
        if 0 <= c < len(self.xs) and 0 <= r < len(self.ys):
            return (self.xs[c], self.ys[r])
        return None

    def _on_mouse_moved(self, evt):
        pos = evt[0]
        if not self.pw.sceneBoundingRect().contains(pos):
            return

        mp = self.pw.getViewBox().mapSceneToView(pos)
        x = int(np.floor(mp.x()))
        y = int(np.floor(mp.y()))

        center = self._pixel_to_center(x, y)
        if center is None:
            return

        self._last_center = center
        self.center_readout.setText(f"spot position =({center[0]}, {center[1]})  (right-click to copy)")

    def _on_mouse_clicked(self, mouse_event):
        if mouse_event.button() != QtCore.Qt.MouseButton.RightButton:
            return

        pos = mouse_event.scenePos()
        mp = self.pw.getViewBox().mapSceneToView(pos)
        x = int(np.floor(mp.x()))
        y = int(np.floor(mp.y()))
        center = self._pixel_to_center(x, y)

        if center is None:
            return
        text = (f"        self.px_slm_phase_mask_position_x = {center[0]}\n"
                f"        self.px_slm_phase_mask_position_y = {center[1]}")
        
        QtWidgets.QApplication.clipboard().setText(text) 
        self.center_readout.setText(f"Copied: {text}")

class ScanWorker(QtCore.QThread):
    progress_sig = QtCore.pyqtSignal(int, int)       
    tile_sig = QtCore.pyqtSignal(int, int, object)   
    finished_sig = QtCore.pyqtSignal(list, int, int) 
    status_sig = QtCore.pyqtSignal(str)

    def __init__(
        self,
        gui_ref,
        centers,
        nx,
        ny,
        settle_s=0.01,
        frame_timeout_s=0.3,
        emit_tiles=True,
        parent=None
    ):
        super().__init__(parent)
        self.gui = gui_ref
        self.centers = list(centers)
        self.nx = int(nx)
        self.ny = int(ny)
        self.settle_s = float(settle_s)
        self.frame_timeout_s = float(frame_timeout_s)
        self.emit_tiles = bool(emit_tiles)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        frames = []
        total = len(self.centers)

        self.status_sig.emit("Scan started...")
        for i, (cx, cy) in enumerate(self.centers):
            if self._stop:
                self.status_sig.emit("Scan aborted.")
                break

            QtCore.QMetaObject.invokeMethod(
                self.gui,
                "set_slm_center_and_update",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(int, int(cx)),
                QtCore.Q_ARG(int, int(cy)),
            )

            time.sleep(self.settle_s)

            frame = self.gui.wait_for_next_frame(timeout_s=self.frame_timeout_s)
            frames.append(frame)

            if self.emit_tiles:
                r = i // self.nx
                c = i % self.nx
                self.tile_sig.emit(r, c, frame)

            self.progress_sig.emit(i + 1, total)

        self.status_sig.emit("Scan finished.")
        self.finished_sig.emit(frames, self.nx, self.ny)


class UnifiedControlGUI(QtWidgets.QMainWindow):
    def __init__(self, camera):
        super().__init__()
        self.setWindowTitle("SLM Andor preview")
        self.resize(1500, 900)

        # Camera
        self.camera = camera
        self.worker = CameraWorker(self.camera)
        self.framebuf = FrameBuffer()
        self.worker.new_frame_sig.connect(self.update_camera_plot)

        # SLM
        self.slm = SLMController(canvas_res=(1920, 1200), server_ip="192.168.1.102", server_port=5000)
        self.slm.state_changed.connect(self._on_slm_state_changed)

        # Scan
        self.scan_worker = None
        self.scan_preview_dlg = None
        self._scan_was_running = True
        self._scan_xs = []
        self._scan_ys = []

        self.init_ui()
        reset_camera_state(self.camera, DummyCamera)
        self._on_slm_state_changed()


    def on_apply_pattern_params(self):
        if self.slm.mode == "spot":
            self.slm.set_spot_radius(self.radius_sb.value())
        else:
            self.slm.set_grating_size(self.grating_size_sb.value())
            self.slm.set_grating_spacing(self.grating_spacing_sb.value())
            self.slm.set_angle_deg(self.angle_sb.value())

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)

        step = 1 if ctrl else 5
        cx, cy = self.slm.get_center()
        moved = False

        if key == QtCore.Qt.Key.Key_Left:
            cx -= step; moved = True
        elif key == QtCore.Qt.Key.Key_Right:
            cx += step; moved = True
        elif key == QtCore.Qt.Key.Key_Up:
            cy -= step; moved = True
        elif key == QtCore.Qt.Key.Key_Down:
            cy += step; moved = True

        if moved:
            self.slm.set_center(cx, cy)
            event.accept()
            return

        plus_keys = {QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Equal}   # '=' is '+' with shift on US keyboard
        minus_keys = {QtCore.Qt.Key.Key_Minus, QtCore.Qt.Key.Key_Underscore}

        if key in plus_keys:
            if self.slm.mode == "spot":
                self.slm.set_spot_radius(self.slm.spot_radius + step)
            else:
                if shift:
                    self.slm.set_grating_spacing(self.slm.grating_spacing + 1)
                else:
                    self.slm.set_grating_size(self.slm.grating_size + step)

            event.accept()
            return

        if key in minus_keys:
            if self.slm.mode == "spot":
                self.slm.set_spot_radius(self.slm.spot_radius - step)
            else:
                if shift:
                    self.slm.set_grating_spacing(self.slm.grating_spacing - 1)
                else:
                    self.slm.set_grating_size(self.slm.grating_size - step)

            event.accept()
            return

        if key == QtCore.Qt.Key.Key_Space and self.slm.mode == "grating":
            self.slm.set_angle_deg(self.slm.angle_deg + (-0.5 if shift else 0.5))
            event.accept()
            return

        super().keyPressEvent(event)



    def init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main = QtWidgets.QHBoxLayout(central)

        sidebar = QtWidgets.QVBoxLayout()
        main.addLayout(sidebar, 1)

        cam_group = QtWidgets.QGroupBox("Camera Control")
        cam_layout = QtWidgets.QVBoxLayout()

        self.video_btn = QtWidgets.QPushButton("Start Video")
        self.video_btn.setCheckable(True)
        self.video_btn.clicked.connect(self.toggle_video)
        cam_layout.addWidget(self.video_btn)

        self.shutter_btn = QtWidgets.QPushButton("Open Shutter")
        self.shutter_btn.setCheckable(True)
        self.shutter_btn.clicked.connect(self.toggle_shutter)
        cam_layout.addWidget(self.shutter_btn)

        cam_group.setLayout(cam_layout)
        sidebar.addWidget(cam_group)

        cam_param_group = QtWidgets.QGroupBox("Camera Params")
        g = QtWidgets.QGridLayout()

        g.addWidget(QtWidgets.QLabel("Exposure (s):"), 0, 0)
        self.exposure_sb = QtWidgets.QDoubleSpinBox()
        self.exposure_sb.setDecimals(4)
        self.exposure_sb.setRange(0.0001, 10.0)
        self.exposure_sb.setSingleStep(0.005)
        self.exposure_sb.setValue(0.05)
        g.addWidget(self.exposure_sb, 0, 1)

        g.addWidget(QtWidgets.QLabel("EM Gain:"), 1, 0)
        self.gain_sb = QtWidgets.QSpinBox()
        self.gain_sb.setRange(0, 1000)
        self.gain_sb.setValue(0)
        g.addWidget(self.gain_sb, 1, 1)

        self.apply_cam_btn = QtWidgets.QPushButton("Apply Camera Params")
        self.apply_cam_btn.clicked.connect(self.on_apply_camera_params)
        g.addWidget(self.apply_cam_btn, 2, 0, 1, 2)

        self.cam_param_status = QtWidgets.QLabel("")
        self.cam_param_status.setStyleSheet("color: gray;")
        g.addWidget(self.cam_param_status, 3, 0, 1, 2)

        cam_param_group.setLayout(g)
        sidebar.addWidget(cam_param_group)

        slm_mode_group = QtWidgets.QGroupBox("SLM Mode")
        h = QtWidgets.QHBoxLayout()
        self.mode_spot_rb = QtWidgets.QRadioButton("Spot")
        self.mode_grating_rb = QtWidgets.QRadioButton("Grating")
        self.mode_spot_rb.setChecked(True)
        self.mode_spot_rb.toggled.connect(self.on_mode_changed)
        h.addWidget(self.mode_spot_rb)
        h.addWidget(self.mode_grating_rb)
        slm_mode_group.setLayout(h)
        sidebar.addWidget(slm_mode_group)

        center_group = QtWidgets.QGroupBox("Pattern Center")
        cg = QtWidgets.QGridLayout()

        cg.addWidget(QtWidgets.QLabel("Center X:"), 0, 0)
        self.center_x_sb = QtWidgets.QSpinBox()
        self.center_x_sb.setRange(0, self.slm.canvas_res[0] - 1)
        cg.addWidget(self.center_x_sb, 0, 1)

        cg.addWidget(QtWidgets.QLabel("Center Y:"), 1, 0)
        self.center_y_sb = QtWidgets.QSpinBox()
        self.center_y_sb.setRange(0, self.slm.canvas_res[1] - 1)
        cg.addWidget(self.center_y_sb, 1, 1)

        self.apply_center_btn = QtWidgets.QPushButton("Apply Center")
        self.apply_center_btn.clicked.connect(self.on_apply_center)
        cg.addWidget(self.apply_center_btn, 2, 0, 1, 2)

        self.center_x_sb.editingFinished.connect(self.on_apply_center)
        self.center_y_sb.editingFinished.connect(self.on_apply_center)

        center_group.setLayout(cg)
        sidebar.addWidget(center_group)

        info_group = QtWidgets.QGroupBox("Pattern Info")
        v = QtWidgets.QVBoxLayout()
        self.coord_label = QtWidgets.QLabel("")
        self.size_label = QtWidgets.QLabel("")
        self.extra_label = QtWidgets.QLabel("")
        v.addWidget(self.coord_label)
        v.addWidget(self.size_label)
        v.addWidget(self.extra_label)
        info_group.setLayout(v)
        sidebar.addWidget(info_group)

        scan_group = QtWidgets.QGroupBox("Scan")
        scan_layout = QtWidgets.QGridLayout()

        scan_layout.addWidget(QtWidgets.QLabel("Range R (px):"), 0, 0)
        self.scan_R_sb = QtWidgets.QSpinBox()
        self.scan_R_sb.setRange(0, 5000)
        self.scan_R_sb.setValue(1)
        scan_layout.addWidget(self.scan_R_sb, 0, 1)

        scan_layout.addWidget(QtWidgets.QLabel("Step (px):"), 1, 0)
        self.scan_step_sb = QtWidgets.QSpinBox()
        self.scan_step_sb.setRange(1, 5000)
        self.scan_step_sb.setValue(1)
        scan_layout.addWidget(self.scan_step_sb, 1, 1)

        scan_layout.addWidget(QtWidgets.QLabel("Preview mode:"), 2, 0)
        self.preview_mode_cb = QtWidgets.QComboBox()
        self.preview_mode_cb.addItems(["no live preview (Fast)", "live preview (Slow)"])
        self.preview_mode_cb.setCurrentIndex(0)
        scan_layout.addWidget(self.preview_mode_cb, 2, 1)

        self.scan_btn = QtWidgets.QPushButton("Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        scan_layout.addWidget(self.scan_btn, 3, 0, 1, 1)

        self.stop_scan_btn = QtWidgets.QPushButton("Stop")
        self.stop_scan_btn.setEnabled(False)
        self.stop_scan_btn.clicked.connect(self.stop_scan)
        scan_layout.addWidget(self.stop_scan_btn, 3, 1, 1, 1)

        self.scan_progress = QtWidgets.QLabel("Idle")
        scan_layout.addWidget(self.scan_progress, 4, 0, 1, 2)

        scan_group.setLayout(scan_layout)
        sidebar.addWidget(scan_group)

      

        # SLM preview
        sidebar.addWidget(QtWidgets.QLabel("SLM Preview:"))
        self.slm_preview = SLMPreviewWidget(self.slm, height=300)
        self.slm_preview.dragged_to.connect(self.slm.set_center)
        sidebar.addWidget(self.slm_preview)

        sidebar.addStretch()

        # Andor window
        self.view = pg.GraphicsLayoutWidget()
        self.plot = self.view.addPlot(title="Andor Live Window")
        self.cam_img_item = pg.ImageItem()
        self.plot.addItem(self.cam_img_item)
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.cam_img_item)
        self.view.addItem(self.hist)
        main.addWidget(self.view, 4)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    # SLM 
    def _on_slm_state_changed(self):
        cx, cy = self.slm.get_center()

        self.center_x_sb.blockSignals(True)
        self.center_y_sb.blockSignals(True)
        self.center_x_sb.setValue(cx)
        self.center_y_sb.setValue(cy)
        self.center_x_sb.blockSignals(False)
        self.center_y_sb.blockSignals(False)

        self.coord_label.setText(f"Center: ({cx}, {cy})")
        if self.slm.mode == "spot":
            self.size_label.setText(f"Radius: {self.slm.spot_radius}")
            self.extra_label.setText("Mode: Spot")
        else:
            self.size_label.setText(f"Size: {self.slm.grating_size}")
            self.extra_label.setText(f"Spacing: {self.slm.grating_spacing} | Angle: {self.slm.angle_deg}°")

        self.slm_preview.refresh()

    def on_mode_changed(self):
        self.slm.set_mode("spot" if self.mode_spot_rb.isChecked() else "grating")

    def on_apply_center(self):
        self.slm.set_center(self.center_x_sb.value(), self.center_y_sb.value())

    # Camera
    def on_apply_camera_params(self):
        ok, msg = apply_camera_params(
            self.camera, DummyCamera, self.worker,
            exposure_s=float(self.exposure_sb.value()),
            gain=int(self.gain_sb.value()),
        )
        self.cam_param_status.setText(msg)

    def toggle_video(self, checked):
        if checked:
            self.worker.start()
        else:
            self.worker.stop()

    def toggle_shutter(self, checked):
        mode = "open" if checked else "closed"
        was_running = self.worker.isRunning()
        if was_running:
            self.worker.stop()
        try:
            self.camera.setup_shutter(mode=mode)
        except Exception:
            pass
        if was_running:
            self.worker.start()

    @QtCore.pyqtSlot(np.ndarray)
    def update_camera_plot(self, data):
        self.cam_img_item.setImage(data.T, autoLevels=True)
        self.framebuf.push(data)

    def wait_for_next_frame(self, timeout_s=1.5):
        return self.framebuf.wait_for_next(timeout_s=timeout_s)

    @QtCore.pyqtSlot(int, int)
    def set_slm_center_and_update(self, cx, cy):
        self.slm.set_center(cx, cy)

    # Scan
    def start_scan(self):
        if self.scan_worker is not None and self.scan_worker.isRunning():
            return

        R = int(self.scan_R_sb.value())
        step = int(self.scan_step_sb.value())

        x0, y0 = self.slm.get_center()
        xs = list(range(x0 - R, x0 + R, step)) if R > 0 else [x0]
        ys = list(range(y0 - R, y0 + R, step)) if R > 0 else [y0]

        xs = [max(0, min(self.slm.canvas_res[0] - 1, x)) for x in xs]
        ys = [max(0, min(self.slm.canvas_res[1] - 1, y)) for y in ys]

        nx, ny = len(xs), len(ys)
        centers = [(x, y) for y in ys for x in xs]

        self._scan_xs = xs
        self._scan_ys = ys

        self._scan_was_running = self.worker.isRunning()
        if not self._scan_was_running:
            self.video_btn.setChecked(True)
            self.worker.start()

        slow_live = (self.preview_mode_cb.currentIndex() == 1)

        if slow_live:
            if self.scan_preview_dlg is not None:
                try:
                    self.scan_preview_dlg.close()
                except Exception:
                    pass
            self.scan_preview_dlg = LiveScanPreviewDialog(
                nx, ny, xs, ys, parent=self, title=f"Scan Preview (live) ({ny}x{nx})"
            )
            self.scan_preview_dlg.show()
        else:
            if self.scan_preview_dlg is not None:
                try:
                    self.scan_preview_dlg.close()
                except Exception:
                    pass
            self.scan_preview_dlg = None

        self.scan_btn.setEnabled(False)
        self.stop_scan_btn.setEnabled(True)
        self.scan_progress.setText(f"Scanning 0/{len(centers)} ...")

        self.scan_worker = ScanWorker(
            gui_ref=self,
            centers=centers,
            nx=nx,
            ny=ny,
            settle_s=0.01,
            frame_timeout_s=0.3,
            emit_tiles=slow_live,
        )
        self.scan_worker.progress_sig.connect(self._on_scan_progress)
        self.scan_worker.status_sig.connect(self._on_scan_status)
        self.scan_worker.finished_sig.connect(self._on_scan_finished)
        if slow_live:
            self.scan_worker.tile_sig.connect(self._on_scan_tile)

        self.scan_worker.start()

    def stop_scan(self):
        """
        Interrupt scan safely.
        Worker will exit loop at next iteration boundary.
        """
        if self.scan_worker is not None and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.scan_progress.setText("Stopping...")
            self.stop_scan_btn.setEnabled(False)

    @QtCore.pyqtSlot(int, int)
    def _on_scan_progress(self, done, total):
        self.scan_progress.setText(f"Scanning {done}/{total} ...")

    @QtCore.pyqtSlot(str)
    def _on_scan_status(self, msg):
        # optional: print(msg)
        pass

    @QtCore.pyqtSlot(int, int, object)
    def _on_scan_tile(self, r, c, frame_obj):
        if self.scan_preview_dlg is None:
            return
        try:
            self.scan_preview_dlg.update_tile(r, c, frame_obj)
        except Exception:
            pass

    @QtCore.pyqtSlot(list, int, int)
    def _on_scan_finished(self, frames_flat, nx, ny):
        self.scan_btn.setEnabled(True)
        self.stop_scan_btn.setEnabled(False)
        self.scan_progress.setText("Idle")

        if not getattr(self, "_scan_was_running", True):
            self.video_btn.setChecked(False)
            self.worker.stop()

        slow_live = (self.preview_mode_cb.currentIndex() == 1)
        if not slow_live:
            grid = []
            idx = 0
            for r in range(ny):
                row = []
                for c in range(nx):
                    row.append(frames_flat[idx] if idx < len(frames_flat) else None)
                    idx += 1
                grid.append(row)

            xs = getattr(self, "_scan_xs", list(range(nx)))
            ys = getattr(self, "_scan_ys", list(range(ny)))

            dlg = FinalScanPreviewDialog(grid, xs, ys, parent=self, title=f"Scan Preview ({ny}x{nx})")
            dlg.exec()

    def closeEvent(self, event):
        try:
            if self.scan_worker is not None and self.scan_worker.isRunning():
                self.scan_worker.stop()
                self.scan_worker.wait(1000)
        except Exception:
            pass

        try:
            if self.scan_preview_dlg is not None:
                self.scan_preview_dlg.close()
        except Exception:
            pass

        try:
            self.worker.stop()
        except Exception:
            pass

        try:
            self.camera.Close()
        except Exception:
            pass

        self.slm.close()
        event.accept()


class UnifiedExperiment(EnvExperiment):
    def build(self):
        try:
            self.camera = AndorEMCCD(ExposureTime=0.05, gain=0.0, hs_speed=0, vs_speed=0)
        except Exception:
            self.camera = DummyCamera()

    def run(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        gui = UnifiedControlGUI(self.camera)
        gui.show()
        app.exec()


if __name__ == "__main__":
    from artiq.frontend.artiq_run import main
    sys.argv.append(__file__)
    main()
