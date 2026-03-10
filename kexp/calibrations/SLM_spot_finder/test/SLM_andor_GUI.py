import sys
import socket
import json
import time
import numpy as np
import threading

from PyQt6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
from PIL import Image, ImageDraw
from artiq.language.environment import EnvExperiment

from waxx.control import AndorEMCCD, DummyCamera


# --- CAMERA WORKER ---
class CameraWorker(QtCore.QThread):
    new_frame_sig = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = False

    def run(self):
        self.running = True
        try:
            self.camera.clear_acquisition()
            self.camera.start_acquisition()
            while self.running:
                try:
                    if self.camera.wait_for_frame(timeout=0.2):
                        frames = self.camera.read_multiple_images(return_info=False)
                        if frames is not None and len(frames) > 0:
                            data = np.asanyarray(frames[-1], dtype=np.uint16)
                            self.new_frame_sig.emit(data)
                except Exception:
                    continue
        finally:
            try:
                self.camera.stop_acquisition()
            except:
                pass

    def stop(self):
        self.running = False
        self.wait()


class LiveScanPreviewDialog(QtWidgets.QDialog):
    """
    Real-time scan preview as ONE mosaic image.
    Coordinates are shown only on LEFT (y) and BOTTOM (x) axes.
    Tiles update live as frames arrive.
    """
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

        layout = QtWidgets.QVBoxLayout(self)
        self.pw = pg.PlotWidget()
        layout.addWidget(self.pw)

        self.pw.setMenuEnabled(False)
        self.pw.setMouseEnabled(x=True, y=True)
        self.pw.setAspectLocked(True)

        self.pw.showAxis('bottom', True)
        self.pw.showAxis('left', True)
        self.pw.showAxis('top', False)
        self.pw.showAxis('right', False)

        self.pw.setLabel('bottom', 'spot center-x')
        self.pw.setLabel('left', 'spot center-y')
        self.pw.invertY(True)

        self.img_item = pg.ImageItem()
        self.pw.addItem(self.img_item)

        self._grid_lines_added = False
        self._msg = pg.TextItem("Waiting for first frame...", anchor=(0, 0))
        self._msg.setPos(0, 0)
        self.pw.addItem(self._msg)

    def _init_with_frame(self, frame: np.ndarray):
        self.H, self.W = frame.shape
        self.mosaic = np.zeros((self.H * self.ny, self.W * self.nx), dtype=frame.dtype)

        x_ticks = [((c + 0.5) * self.W, str(self.xs[c])) for c in range(self.nx)]
        y_ticks = [((r + 0.5) * self.H, str(self.ys[r])) for r in range(self.ny)]
        self.pw.getAxis('bottom').setTicks([x_ticks])
        self.pw.getAxis('left').setTicks([y_ticks])

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
    """
    Final (non-live) scan preview as ONE mosaic image.
    Coordinates are shown only on LEFT (y) and BOTTOM (x) axes.
    """
    def __init__(self, frames_grid, xs, ys, parent=None, title="Scan Preview"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 800)

        ny = len(frames_grid)
        nx = len(frames_grid[0]) if ny > 0 else 0

        sample = None
        for r in range(ny):
            for c in range(nx):
                if frames_grid[r][c] is not None:
                    sample = frames_grid[r][c]
                    break
            if sample is not None:
                break

        if sample is None:
            layout = QtWidgets.QVBoxLayout(self)
            layout.addWidget(QtWidgets.QLabel("No frames captured."))
            return

        H, W = sample.shape
        mosaic = np.zeros((H * ny, W * nx), dtype=sample.dtype)

        for r in range(ny):
            for c in range(nx):
                fr = frames_grid[r][c]
                if fr is None:
                    continue
                mosaic[r * H:(r + 1) * H, c * W:(c + 1) * W] = fr

        layout = QtWidgets.QVBoxLayout(self)
        self.pw = pg.PlotWidget()
        layout.addWidget(self.pw)

        self.pw.setMenuEnabled(False)
        self.pw.setMouseEnabled(x=True, y=True)
        self.pw.setAspectLocked(True)

        self.pw.showAxis('bottom', True)
        self.pw.showAxis('left', True)
        self.pw.showAxis('top', False)
        self.pw.showAxis('right', False)

        self.pw.setLabel('bottom', 'spot center-x')
        self.pw.setLabel('left', 'spot center-y')
        self.pw.invertY(True)

        img_item = pg.ImageItem()
        self.pw.addItem(img_item)
        img_item.setImage(mosaic.T, autoLevels=True)

        x_ticks = [((c + 0.5) * W, str(xs[c])) for c in range(nx)]
        y_ticks = [((r + 0.5) * H, str(ys[r])) for r in range(ny)]
        self.pw.getAxis('bottom').setTicks([x_ticks])
        self.pw.getAxis('left').setTicks([y_ticks])

        for c in range(1, nx):
            x = c * W
            line = pg.InfiniteLine(pos=x, angle=90, movable=False)
            line.setZValue(10)
            self.pw.addItem(line)

        for r in range(1, ny):
            y = r * H
            line = pg.InfiniteLine(pos=y, angle=0, movable=False)
            line.setZValue(10)
            self.pw.addItem(line)


class ScanWorker(QtCore.QThread):
    progress_sig = QtCore.pyqtSignal(int, int)              # (done, total)
    tile_sig = QtCore.pyqtSignal(int, int, object)          # (r, c, frame)
    finished_sig = QtCore.pyqtSignal(list, int, int)        # frames_flat, nx, ny
    status_sig = QtCore.pyqtSignal(str)

    def __init__(
        self,
        gui_ref,
        centers,
        nx,
        ny,
        settle_s=0.02,
        frame_timeout_s=1.5,
        emit_tiles=True,
        parent=None
    ):
        super().__init__(parent)
        self.gui = gui_ref
        self.centers = centers
        self.nx = nx
        self.ny = ny
        self.settle_s = settle_s
        self.frame_timeout_s = frame_timeout_s
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
                QtCore.Q_ARG(int, cx),
                QtCore.Q_ARG(int, cy),
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


# --- MAIN UNIFIED GUI ---
class UnifiedControlGUI(QtWidgets.QMainWindow):
    def __init__(self, camera):
        super().__init__()
        self.setWindowTitle("Unified SLM Control & Andor Preview")
        self.resize(1500, 900)

        self.camera = camera
        self.worker = CameraWorker(self.camera)
        self.worker.new_frame_sig.connect(self.update_camera_plot)

        # ---- Latest frame bookkeeping for scan ----
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._frame_id = 0
        self._frame_wait = threading.Condition(self._frame_lock)

        # SLM State
        self.canvas_res = (1920, 1200)
        self.spot_center = [994, 824]
        self.spot_radius = 10
        self.grating_center = [994, 824]
        self.grating_size = 300
        self.grating_spacing = 6
        self.angle_deg = 0.0
        self.mode = "spot"
        self.dragging = False

        self.scan_worker = None
        self.scan_preview_dlg = None

        # Networking
        self.server_ip = "192.168.1.102"
        self.server_port = 5000
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((self.server_ip, self.server_port))
            print("Connected to SLM server.")
        except Exception as e:
            print(f"SLM Connection Failed: {e}")
            self.sock = None

        self.init_ui()
        self.reset_camera_state()
        self._sync_center_boxes_from_state()

    def reset_camera_state(self):
        if isinstance(self.camera, DummyCamera):
            return
        try:
            self.camera.stop_acquisition()
            self.camera.set_trigger_mode("int")
            self.camera.set_acquisition_mode("cont")
            self.camera.set_EMCCD_gain(0)
        except Exception as e:
            print(f"Camera Reset Error: {e}")

    # ---------------- UI ----------------
    def init_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QHBoxLayout(central_widget)

        # --- LEFT: SIDEBAR ---
        sidebar = QtWidgets.QVBoxLayout()

        # Camera Control Group
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

        # Camera Params Group (Exposure + Gain)
        cam_param_group = QtWidgets.QGroupBox("Camera Params")
        cam_param_layout = QtWidgets.QGridLayout()

        cam_param_layout.addWidget(QtWidgets.QLabel("Exposure (s):"), 0, 0)
        self.exposure_sb = QtWidgets.QDoubleSpinBox()
        self.exposure_sb.setDecimals(4)
        self.exposure_sb.setRange(0.0001, 10.0)
        self.exposure_sb.setSingleStep(0.005)
        self.exposure_sb.setValue(0.05)  # default matches your AndorEMCCD init
        cam_param_layout.addWidget(self.exposure_sb, 0, 1)

        cam_param_layout.addWidget(QtWidgets.QLabel("EM Gain:"), 1, 0)
        self.gain_sb = QtWidgets.QSpinBox()
        self.gain_sb.setRange(0, 1000)
        self.gain_sb.setSingleStep(5)
        self.gain_sb.setValue(0)
        cam_param_layout.addWidget(self.gain_sb, 1, 1)

        self.apply_cam_btn = QtWidgets.QPushButton("Apply Camera Params")
        self.apply_cam_btn.clicked.connect(self.apply_camera_params)
        cam_param_layout.addWidget(self.apply_cam_btn, 2, 0, 1, 2)

        self.cam_param_status = QtWidgets.QLabel("")
        self.cam_param_status.setStyleSheet("color: gray;")
        cam_param_layout.addWidget(self.cam_param_status, 3, 0, 1, 2)

        cam_param_group.setLayout(cam_param_layout)
        sidebar.addWidget(cam_param_group)

        # SLM Mode Group
        slm_group = QtWidgets.QGroupBox("SLM Mode")
        slm_layout = QtWidgets.QHBoxLayout()
        self.mode_spot_rb = QtWidgets.QRadioButton("Spot (1)")
        self.mode_spot_rb.setChecked(True)
        self.mode_grating_rb = QtWidgets.QRadioButton("Grating (2)")
        self.mode_spot_rb.toggled.connect(self.update_slm_mode)
        slm_layout.addWidget(self.mode_spot_rb)
        slm_layout.addWidget(self.mode_grating_rb)
        slm_group.setLayout(slm_layout)
        sidebar.addWidget(slm_group)

        # Pattern Center Group (type center x,y)
        center_group = QtWidgets.QGroupBox("Pattern Center")
        center_layout = QtWidgets.QGridLayout()

        center_layout.addWidget(QtWidgets.QLabel("Center X:"), 0, 0)
        self.center_x_sb = QtWidgets.QSpinBox()
        self.center_x_sb.setRange(0, self.canvas_res[0] - 1)
        self.center_x_sb.setValue(self.spot_center[0])
        center_layout.addWidget(self.center_x_sb, 0, 1)

        center_layout.addWidget(QtWidgets.QLabel("Center Y:"), 1, 0)
        self.center_y_sb = QtWidgets.QSpinBox()
        self.center_y_sb.setRange(0, self.canvas_res[1] - 1)
        self.center_y_sb.setValue(self.spot_center[1])
        center_layout.addWidget(self.center_y_sb, 1, 1)

        self.apply_center_btn = QtWidgets.QPushButton("Apply Center")
        self.apply_center_btn.clicked.connect(self.apply_center_from_boxes)
        center_layout.addWidget(self.apply_center_btn, 2, 0, 1, 2)

        # Nice: pressing Enter in spinbox will apply (editingFinished)
        self.center_x_sb.editingFinished.connect(self.apply_center_from_boxes)
        self.center_y_sb.editingFinished.connect(self.apply_center_from_boxes)

        center_group.setLayout(center_layout)
        sidebar.addWidget(center_group)

        # SLM Info Display
        info_group = QtWidgets.QGroupBox("Pattern Info")
        info_layout = QtWidgets.QVBoxLayout()
        self.coord_label = QtWidgets.QLabel("Center: (0, 0)")
        self.size_label = QtWidgets.QLabel("Size/Radius: 0")
        self.extra_label = QtWidgets.QLabel("Spacing: 0 | Angle: 0")
        info_layout.addWidget(self.coord_label)
        info_layout.addWidget(self.size_label)
        info_layout.addWidget(self.extra_label)
        info_group.setLayout(info_layout)
        sidebar.addWidget(info_group)

        # ---- SCAN CONTROLS ----
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
        scan_layout.addWidget(self.scan_btn, 3, 0, 1, 2)

        self.scan_progress = QtWidgets.QLabel("Idle")
        scan_layout.addWidget(self.scan_progress, 4, 0, 1, 2)

        scan_group.setLayout(scan_layout)
        sidebar.addWidget(scan_group)

        # ---- SLM Preview Mini-Canvas ----
        sidebar.addWidget(QtWidgets.QLabel("SLM Preview:"))
        self.slm_preview = pg.GraphicsLayoutWidget()
        self.slm_preview.setFixedHeight(300)
        self.slm_plot = self.slm_preview.addPlot()

        self.slm_plot.hideAxis("bottom")
        self.slm_plot.hideAxis("left")
        self.slm_plot.hideAxis("top")
        self.slm_plot.hideAxis("right")

        self.slm_plot.setMenuEnabled(False)
        vb = self.slm_plot.getViewBox()
        vb.setMouseEnabled(x=False, y=False)   # canvas not draggable
        vb.setMenuEnabled(False)
        vb.setDefaultPadding(0.0)

        self.slm_plot.invertY(True)            # fix upside-down
        self.slm_plot.setAspectLocked(True)

        self.slm_img_item = pg.ImageItem()
        self.slm_plot.addItem(self.slm_img_item)

        # only pattern draggable
        self.slm_img_item.mousePressEvent = self.start_drag
        self.slm_img_item.mouseMoveEvent = self.do_drag
        self.slm_img_item.mouseReleaseEvent = self.stop_drag

        sidebar.addWidget(self.slm_preview)

        sidebar.addStretch()
        main_layout.addLayout(sidebar, 1)

        # --- RIGHT: CAMERA VIEW ---
        self.view = pg.GraphicsLayoutWidget()
        self.plot = self.view.addPlot(title="Andor Live Window")
        self.cam_img_item = pg.ImageItem()
        self.plot.addItem(self.cam_img_item)
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.cam_img_item)
        self.view.addItem(self.hist)
        main_layout.addWidget(self.view, 4)

        self.refresh_slm_preview()
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    # ---------------- helpers ----------------
    def _get_active_center_ref(self):
        return self.spot_center if self.mode == "spot" else self.grating_center

    def _sync_center_boxes_from_state(self):
        cx, cy = self.get_current_center()
        # block signals to avoid triggering apply_center_from_boxes while we update UI
        self.center_x_sb.blockSignals(True)
        self.center_y_sb.blockSignals(True)
        self.center_x_sb.setValue(int(cx))
        self.center_y_sb.setValue(int(cy))
        self.center_x_sb.blockSignals(False)
        self.center_y_sb.blockSignals(False)

    # ---------------- KEYBOARD CONTROLS ----------------
    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        ctrl = modifiers & QtCore.Qt.KeyboardModifier.ControlModifier
        shift = modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier
        step = 1 if ctrl else 5

        if key == QtCore.Qt.Key.Key_1:
            self.mode_spot_rb.setChecked(True)
        elif key == QtCore.Qt.Key.Key_2:
            self.mode_grating_rb.setChecked(True)

        center = self._get_active_center_ref()

        if key == QtCore.Qt.Key.Key_Left:
            center[0] -= step
        elif key == QtCore.Qt.Key.Key_Right:
            center[0] += step
        elif key == QtCore.Qt.Key.Key_Up:
            center[1] -= step
        elif key == QtCore.Qt.Key.Key_Down:
            center[1] += step

        elif key in [QtCore.Qt.Key.Key_Plus, QtCore.Qt.Key.Key_Equal]:
            if self.mode == "spot":
                self.spot_radius += step
            else:
                if shift:
                    self.grating_spacing += 1
                else:
                    self.grating_size += step

        elif key in [QtCore.Qt.Key.Key_Minus, QtCore.Qt.Key.Key_Underscore]:
            if self.mode == "spot":
                self.spot_radius = max(1, self.spot_radius - step)
            else:
                if shift:
                    self.grating_spacing = max(2, self.grating_spacing - 1)
                else:
                    self.grating_size = max(2, self.grating_size - step)

        elif key == QtCore.Qt.Key.Key_Space:
            self.angle_deg += -0.5 if shift else 0.5

        # clamp center to canvas bounds
        center[0] = max(0, min(self.canvas_res[0] - 1, int(center[0])))
        center[1] = max(0, min(self.canvas_res[1] - 1, int(center[1])))

        self.refresh_slm_preview()
        self.send_slm_update()
        self._sync_center_boxes_from_state()

    # ---------------- SLM LOGIC ----------------
    def update_slm_mode(self):
        self.mode = "spot" if self.mode_spot_rb.isChecked() else "grating"
        self.refresh_slm_preview()
        self.send_slm_update()
        self._sync_center_boxes_from_state()

    def apply_center_from_boxes(self):
        cx = int(self.center_x_sb.value())
        cy = int(self.center_y_sb.value())
        self.set_slm_center_and_update(cx, cy)

    def refresh_slm_preview(self):
        img = Image.new("L", self.canvas_res, 255)
        draw = ImageDraw.Draw(img)

        if self.mode == "spot":
            x, y = self.spot_center
            r = self.spot_radius
            draw.ellipse((x - r, y - r, x + r, y + r), fill=0)
            self.coord_label.setText(f"Center: ({x}, {y})")
            self.size_label.setText(f"Radius: {r}")
            self.extra_label.setText("Mode: Spot")
        else:
            cx, cy = self.grating_center
            half = self.grating_size // 2
            period = self.grating_spacing
            theta = np.deg2rad(self.angle_deg)
            c, s = np.cos(theta), np.sin(theta)

            for y in range(max(0, cy - half), min(self.canvas_res[1], cy + half)):
                for x in range(max(0, cx - half), min(self.canvas_res[0], cx + half)):
                    proj = (x - cx) * c + (y - cy) * s
                    if (proj % period) < (period * 0.5):
                        draw.point((x, y), fill=0)

            self.coord_label.setText(f"Center: ({cx}, {cy})")
            self.size_label.setText(f"Size: {self.grating_size}")
            self.extra_label.setText(f"Spacing: {period} | Angle: {self.angle_deg}°")

        self.slm_img_item.setImage(np.array(img).T)

    def start_drag(self, event):
        self.dragging = True

    def stop_drag(self, event):
        self.dragging = False

    def do_drag(self, event):
        if self.dragging:
            pos = event.pos()
            cx = max(0, min(self.canvas_res[0] - 1, int(pos.x())))
            cy = max(0, min(self.canvas_res[1] - 1, int(pos.y())))
            if self.mode == "spot":
                self.spot_center = [cx, cy]
            else:
                self.grating_center = [cx, cy]
            self.refresh_slm_preview()
            self.send_slm_update()
            self._sync_center_boxes_from_state()

    def send_slm_update(self):
        if not self.sock:
            return
        try:
            center = self.spot_center if self.mode == "spot" else self.grating_center
            dim = self.spot_radius if self.mode == "spot" else self.grating_size
            command = {
                "mask": self.mode,
                "center": center,
                "dimension": dim,
                "spacing": self.grating_spacing,
                "angle": self.angle_deg,
                "phase": 3,
                "initialize": False,
            }
            self.sock.sendall(json.dumps(command).encode() + b"\n")
        except Exception as e:
            print(f"Send Error: {e}")

    # ---------------- CAMERA PARAMS (gain/exposure) ----------------
    def apply_camera_params(self):
        """
        Applies exposure + gain safely:
        - If video is running: stop worker, apply changes, restart.
        - Works only if camera object supports the methods (Andor). DummyCamera is ignored.
        """
        if isinstance(self.camera, DummyCamera):
            self.cam_param_status.setText("DummyCamera: params ignored.")
            return

        exp_s = float(self.exposure_sb.value())
        gain = int(self.gain_sb.value())

        was_running = self.worker.isRunning()
        if was_running:
            try:
                self.worker.stop()
            except Exception:
                pass

        ok = True
        msgs = []

        # Apply exposure (different APIs may exist; try common names)
        try:
            if hasattr(self.camera, "set_exposure_time"):
                self.camera.set_exposure_time(exp_s)
                msgs.append(f"exposure={exp_s:.4f}s")
            elif hasattr(self.camera, "set_ExposureTime"):
                self.camera.set_ExposureTime(exp_s)
                msgs.append(f"exposure={exp_s:.4f}s")
            elif hasattr(self.camera, "ExposureTime"):
                # some wrappers expose attribute
                setattr(self.camera, "ExposureTime", exp_s)
                msgs.append(f"exposure={exp_s:.4f}s")
            else:
                msgs.append("exposure: (method not found)")
        except Exception as e:
            ok = False
            msgs.append(f"exposure error: {e}")

        # Apply gain (you already use set_EMCCD_gain in reset)
        try:
            if hasattr(self.camera, "set_EMCCD_gain"):
                self.camera.set_EMCCD_gain(gain)
                msgs.append(f"gain={gain}")
            else:
                msgs.append("gain: (method not found)")
        except Exception as e:
            ok = False
            msgs.append(f"gain error: {e}")

        # Restart acquisition if it was running
        if was_running:
            try:
                self.worker.start()
            except Exception:
                pass

        self.cam_param_status.setText(("Applied: " if ok else "Partial: ") + " | ".join(msgs))

    # ---------------- CAMERA LOGIC ----------------
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
        self.camera.setup_shutter(mode=mode)
        if was_running:
            self.worker.start()

    @QtCore.pyqtSlot(np.ndarray)
    def update_camera_plot(self, data):
        self.cam_img_item.setImage(data.T, autoLevels=True)

        with self._frame_wait:
            self._latest_frame = data.copy()
            self._frame_id += 1
            self._frame_wait.notify_all()

    def get_current_center(self):
        center = self.spot_center if self.mode == "spot" else self.grating_center
        return int(center[0]), int(center[1])

    def wait_for_next_frame(self, timeout_s=1.5):
        with self._frame_wait:
            start_id = self._frame_id
            t0 = time.time()
            while self._frame_id == start_id:
                remaining = timeout_s - (time.time() - t0)
                if remaining <= 0:
                    break
                self._frame_wait.wait(timeout=remaining)

            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    @QtCore.pyqtSlot(int, int)
    def set_slm_center_and_update(self, cx, cy):
        cx = max(0, min(self.canvas_res[0] - 1, int(cx)))
        cy = max(0, min(self.canvas_res[1] - 1, int(cy)))
        if self.mode == "spot":
            self.spot_center = [cx, cy]
        else:
            self.grating_center = [cx, cy]
        self.refresh_slm_preview()
        self.send_slm_update()
        self._sync_center_boxes_from_state()

    # ---- SCAN LOGIC (FAST/SLOW) ----
    def start_scan(self):
        if self.scan_worker is not None and self.scan_worker.isRunning():
            return

        R = int(self.scan_R_sb.value())
        step = int(self.scan_step_sb.value())
        x0, y0 = self.get_current_center()

        xs = list(range(x0 - R, x0 + R, step)) if R > 0 else [x0]
        ys = list(range(y0 - R, y0 + R, step)) if R > 0 else [y0]

        xs = [max(0, min(self.canvas_res[0] - 1, x)) for x in xs]
        ys = [max(0, min(self.canvas_res[1] - 1, y)) for y in ys]

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
            self.scan_preview_dlg = LiveScanPreviewDialog(nx, ny, xs, ys, parent=self, title=f"Scan Preview (live) ({ny}x{nx})")
            self.scan_preview_dlg.show()
        else:
            if self.scan_preview_dlg is not None:
                try:
                    self.scan_preview_dlg.close()
                except Exception:
                    pass
            self.scan_preview_dlg = None

        self.scan_btn.setEnabled(False)
        self.scan_progress.setText(f"Scanning 0/{len(centers)} ...")

        self.scan_worker = ScanWorker(
            gui_ref=self,
            centers=centers,
            nx=nx,
            ny=ny,
            settle_s=0.02,
            frame_timeout_s=1.5,
            emit_tiles=slow_live,
        )
        self.scan_worker.progress_sig.connect(self._on_scan_progress)
        self.scan_worker.status_sig.connect(self._on_scan_status)
        self.scan_worker.finished_sig.connect(self._on_scan_finished)

        if slow_live:
            self.scan_worker.tile_sig.connect(self._on_scan_tile)

        self.scan_worker.start()

    @QtCore.pyqtSlot(int, int)
    def _on_scan_progress(self, done, total):
        self.scan_progress.setText(f"Scanning {done}/{total} ...")

    @QtCore.pyqtSlot(str)
    def _on_scan_status(self, msg):
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
        except:
            pass

        try:
            if self.scan_preview_dlg is not None:
                self.scan_preview_dlg.close()
        except:
            pass

        self.worker.stop()
        self.camera.Close()
        if self.sock:
            self.sock.close()
        event.accept()


# --- ARTIQ WRAPPER ---
class UnifiedExperiment(EnvExperiment):
    def build(self):
        try:
            self.camera = AndorEMCCD(ExposureTime=0.05, gain=0.0, hs_speed=0, vs_speed=0)
        except:
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
