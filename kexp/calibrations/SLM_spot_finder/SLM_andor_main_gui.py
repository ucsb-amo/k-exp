import sys
import time
import numpy as np
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg

from waxx.control import AndorEMCCD, DummyCamera

from andor_group import CameraWorker, reset_camera_state, apply_camera_params
from slm_group import SLMController, SLMPreviewWidget
from scan_group import ScanWorker, scan_grid, shots_to_grid
from stage_group import StageGroup, POSITION_IN
from status_widgets import StatusPill, BackgroundCall


def mark_missing_tile(plot_widget, r, c, W, H):
    """A red X over a tile that has no frame, so it is not read as a dark frame."""
    x0, y0 = c * W, r * H
    pen = pg.mkPen((220, 40, 40), width=2)
    for xs, ys in (([x0, x0 + W], [y0, y0 + H]), ([x0, x0 + W], [y0 + H, y0])):
        item = pg.PlotDataItem(xs, ys, pen=pen)
        item.setZValue(20)
        plot_widget.addItem(item)


class LiveScanPreviewDialog(QtWidgets.QDialog):
    spot_picked = QtCore.pyqtSignal(int, int)  # (cx, cy) of the left-clicked tile

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
        self._missing = []  # (r, c) of positions that produced no frame

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

        self.note = QtWidgets.QLabel("")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.center_readout = QtWidgets.QLabel("left-click a tile to move the spot there")
        self.center_readout.setStyleSheet("color: gray;")
        layout.addWidget(self.center_readout)
        self.pw.scene().sigMouseClicked.connect(self._on_mouse_clicked)

    def set_note(self, text):
        self.note.setText(text)

    def _pixel_to_center(self, x: int, y: int):
        if not self._initialized:
            return None
        if x < 0 or y < 0 or x >= self.W * self.nx or y >= self.H * self.ny:
            return None
        c = x // self.W
        r = y // self.H
        if 0 <= c < len(self.xs) and 0 <= r < len(self.ys):
            return (self.xs[c], self.ys[r])
        return None

    def _on_mouse_clicked(self, mouse_event):
        if mouse_event.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        mp = self.pw.getViewBox().mapSceneToView(mouse_event.scenePos())
        center = self._pixel_to_center(int(np.floor(mp.x())), int(np.floor(mp.y())))
        if center is None:
            return

        self.center_readout.setText(f"Spot set to ({center[0]}, {center[1]})")
        self.spot_picked.emit(int(center[0]), int(center[1]))

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

        # positions that failed before the first frame arrived
        for r, c in self._missing:
            mark_missing_tile(self.pw, r, c, self.W, self.H)

    @QtCore.pyqtSlot(int, int, object)
    def update_tile(self, r: int, c: int, frame_obj):
        if frame_obj is None:
            self._missing.append((r, c))
            if self._initialized:
                mark_missing_tile(self.pw, r, c, self.W, self.H)
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
    spot_picked = QtCore.pyqtSignal(int, int)  # (cx, cy) of the left-clicked tile

    def __init__(self, frames_grid, xs, ys, parent=None, title="Scan Preview", note=""):
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
            layout.addWidget(QtWidgets.QLabel("No frames captured." + (f"\n{note}" if note else "")))
            return

        self.H, self.W = sample.shape

        missing = []
        self.mosaic = np.zeros((self.H * self.ny, self.W * self.nx), dtype=sample.dtype)
        for r in range(self.ny):
            for c in range(self.nx):
                fr = frames_grid[r][c]
                if fr is None or fr.shape != (self.H, self.W):
                    missing.append((r, c))
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
        for r, c in missing:
            mark_missing_tile(self.pw, r, c, self.W, self.H)

        if note:
            note_label = QtWidgets.QLabel(note)
            note_label.setWordWrap(True)
            layout.addWidget(note_label)

        self.center_readout = QtWidgets.QLabel("center=(?, ?)  (left-click to set spot, right-click to copy)")
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
        self.center_readout.setText(
            f"spot position =({center[0]}, {center[1]})  (left-click to set spot, right-click to copy)"
        )

    def _on_mouse_clicked(self, mouse_event):
        button = mouse_event.button()
        if button not in (QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.RightButton):
            return

        pos = mouse_event.scenePos()
        mp = self.pw.getViewBox().mapSceneToView(pos)
        x = int(np.floor(mp.x()))
        y = int(np.floor(mp.y()))
        center = self._pixel_to_center(x, y)

        if center is None:
            return

        if button == QtCore.Qt.MouseButton.LeftButton:
            self.center_readout.setText(f"Spot set to ({center[0]}, {center[1]})")
            self.spot_picked.emit(int(center[0]), int(center[1]))
            return

        text = (f"        self.px_slm_phase_mask_position_x = {center[0]}\n"
                f"        self.px_slm_phase_mask_position_y = {center[1]}")

        QtWidgets.QApplication.clipboard().setText(text)
        self.center_readout.setText(f"Copied: {text}")


class SidebarScrollArea(QtWidgets.QScrollArea):
    """Lets the sidebar scroll on a short screen without taking the arrow keys.

    A scroll area scrolls on arrow keys; passing them on keeps them what they
    have always been here -- nudging the SLM pattern (UnifiedControlGUI.keyPressEvent).
    """

    def keyPressEvent(self, event):
        event.ignore()


class UnifiedControlGUI(QtWidgets.QMainWindow):
    RADIUS_MIN = 1
    RADIUS_MAX = 600

    def __init__(self, camera=None, connect_camera_on_start=True):
        super().__init__()
        self.setWindowTitle("SLM Andor preview")
        self.resize(1500, 900)
        self._closing = False

        # Camera. DummyCamera stands in while the Andor is not connected; the
        # andor button connects and releases it without closing the window.
        self.camera = camera if camera is not None else DummyCamera()
        self._camera_busy = ""   # "connecting" / "disconnecting" while under way
        self._camera_error = ""
        self.worker = CameraWorker(self.camera)
        self.worker.new_frame_sig.connect(self.update_camera_plot)
        self.worker.finished.connect(self._on_video_stopped)

        # SLM
        self.slm = SLMController(canvas_res=(1920, 1200), server_ip="192.168.1.102", server_port=5000)
        self.slm.state_changed.connect(self._on_slm_state_changed)
        self.slm.link_changed.connect(self._on_slm_link_changed)

        # Scan
        self.scan_worker = None
        self.scan_preview_dlg = None
        self._scanning = False
        self._scan_live = False
        self._scan_was_running = False
        self._scan_xs = []
        self._scan_ys = []
        self._scan_total = 0
        self._scan_done = 0
        self._scan_last_t = None
        self._scan_start_center = None
        self._scan_picked = False
        self._scan_restore_pending = False

        self.init_ui()
        if self._camera_connected():
            reset_camera_state(self.camera, DummyCamera)
        self._on_slm_state_changed()
        self._update_controls()

        self.slm.check_link()
        # Connecting reads the stage position; it never moves the stage.
        QtCore.QTimer.singleShot(0, self.stage_group.connect_stage)
        if connect_camera_on_start and not self._camera_connected():
            QtCore.QTimer.singleShot(0, self.connect_camera)


    def on_apply_pattern_params(self):
        if self.slm.mode == "spot":
            self.slm.set_spot_radius(self.radius_sb.value())
        else:
            self.slm.set_grating_size(self.grating_size_sb.value())
            self.slm.set_grating_spacing(self.grating_spacing_sb.value())
            self.slm.set_angle_deg(self.angle_sb.value())

    def keyPressEvent(self, event):
        # The scan owns the pattern while it runs; a nudge now would put the
        # next frame at a position other than the one it is filed under.
        if self._scanning:
            super().keyPressEvent(event)
            return

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

        # The sidebar is taller than most screens, so it scrolls.
        sidebar_widget = QtWidgets.QWidget()
        sidebar = QtWidgets.QVBoxLayout(sidebar_widget)
        sidebar_scroll = SidebarScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        sidebar_scroll.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        sidebar_scroll.setWidget(sidebar_widget)
        main.addWidget(sidebar_scroll, 1)

        # Connections: the same coloured buttons as liveOD's camera row. Grey
        # not connected, purple connecting, green connected, blue acquiring,
        # red failed; hover for the detail.
        self.stage_group = StageGroup()

        conn_row = QtWidgets.QHBoxLayout()
        conn_row.addWidget(QtWidgets.QLabel("Connections:"))
        self.camera_pill = StatusPill("andor")
        self.camera_pill.clicked.connect(self._on_camera_pill_clicked)
        conn_row.addWidget(self.camera_pill)
        self.slm_pill = StatusPill("slm")
        self.slm_pill.set_state("closed", "Not checked yet.", action="check the SLM server")
        self.slm_pill.clicked.connect(self.slm.check_link)
        conn_row.addWidget(self.slm_pill)
        conn_row.addWidget(self.stage_group.pill)
        conn_row.addStretch()
        sidebar.addLayout(conn_row)

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
        self.gain_sb.setRange(0, 100)
        self.gain_sb.setValue(0)
        g.addWidget(self.gain_sb, 1, 1)

        self.apply_cam_btn = QtWidgets.QPushButton("Apply Camera Params")
        self.apply_cam_btn.clicked.connect(self.on_apply_camera_params)
        g.addWidget(self.apply_cam_btn, 2, 0, 1, 2)

        self.cam_param_status = QtWidgets.QLabel("")
        self.cam_param_status.setStyleSheet("color: gray;")
        self.cam_param_status.setWordWrap(True)
        g.addWidget(self.cam_param_status, 3, 0, 1, 2)

        cam_param_group.setLayout(g)
        sidebar.addWidget(cam_param_group)

        sidebar.addWidget(self.stage_group)

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

        self.reset_center_btn = QtWidgets.QPushButton("Reset to Default")
        self.reset_center_btn.clicked.connect(self.on_reset_center)
        cg.addWidget(self.reset_center_btn, 3, 0, 1, 2)

        self.center_x_sb.editingFinished.connect(self.on_apply_center)
        self.center_y_sb.editingFinished.connect(self.on_apply_center)

        center_group.setLayout(cg)
        sidebar.addWidget(center_group)

        size_group = QtWidgets.QGroupBox("Spot Size")
        sz = QtWidgets.QGridLayout()

        sz.addWidget(QtWidgets.QLabel("Radius (px):"), 0, 0)
        self.radius_sb = QtWidgets.QSpinBox()
        self.radius_sb.setRange(self.RADIUS_MIN, self.RADIUS_MAX)
        self.radius_sb.setValue(self.slm.spot_radius)
        self.radius_sb.valueChanged.connect(self.on_spot_radius_changed)
        sz.addWidget(self.radius_sb, 0, 1)

        self.radius_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.radius_slider.setRange(self.RADIUS_MIN, self.RADIUS_MAX)
        self.radius_slider.setValue(self.slm.spot_radius)
        self.radius_slider.valueChanged.connect(self.on_spot_radius_changed)
        sz.addWidget(self.radius_slider, 1, 0, 1, 2)

        self.size_group = size_group
        size_group.setLayout(sz)
        sidebar.addWidget(size_group)

        # everything that moves the pattern; locked while a scan owns it
        self._pattern_groups = (slm_mode_group, center_group)

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

        scan_layout.addWidget(QtWidgets.QLabel("Range ±R (px):"), 0, 0)
        self.scan_R_sb = QtWidgets.QSpinBox()
        self.scan_R_sb.setRange(0, 5000)
        self.scan_R_sb.setValue(1)
        scan_layout.addWidget(self.scan_R_sb, 0, 1)

        scan_layout.addWidget(QtWidgets.QLabel("Step (px):"), 1, 0)
        self.scan_step_sb = QtWidgets.QSpinBox()
        self.scan_step_sb.setRange(1, 5000)
        self.scan_step_sb.setValue(1)
        scan_layout.addWidget(self.scan_step_sb, 1, 1)

        scan_layout.addWidget(QtWidgets.QLabel("SLM settle (ms):"), 2, 0)
        self.settle_sb = QtWidgets.QSpinBox()
        self.settle_sb.setRange(0, 5000)
        self.settle_sb.setSingleStep(10)
        self.settle_sb.setValue(150)
        self.settle_sb.setToolTip(
            "Wait between the SLM server reporting a pattern applied and the start of "
            "the exposure, for the SLM's next video frame and liquid-crystal response.\n"
            "With an SLM server that does not report (the old run_server.py) it counts "
            "from the send instead, and must also cover the server's own processing.")
        scan_layout.addWidget(self.settle_sb, 2, 1)

        scan_layout.addWidget(QtWidgets.QLabel("Preview mode:"), 3, 0)
        self.preview_mode_cb = QtWidgets.QComboBox()
        # Scan timing no longer depends on the GUI, so live preview costs only
        # redraw time -- the GUI may lag on a big grid, the frames do not.
        self.preview_mode_cb.addItems(["final preview only", "live preview (GUI may lag)"])
        self.preview_mode_cb.setCurrentIndex(0)
        scan_layout.addWidget(self.preview_mode_cb, 3, 1)

        self.return_to_start_cb = QtWidgets.QCheckBox("Return to start position after scan")
        self.return_to_start_cb.setChecked(True)
        scan_layout.addWidget(self.return_to_start_cb, 4, 0, 1, 2)

        self.scan_btn = QtWidgets.QPushButton("Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        scan_layout.addWidget(self.scan_btn, 5, 0, 1, 1)

        self.stop_scan_btn = QtWidgets.QPushButton("Stop")
        self.stop_scan_btn.setEnabled(False)
        self.stop_scan_btn.clicked.connect(self.stop_scan)
        scan_layout.addWidget(self.stop_scan_btn, 5, 1, 1, 1)

        self.scan_progress = QtWidgets.QLabel("Idle")
        self.scan_progress.setWordWrap(True)
        scan_layout.addWidget(self.scan_progress, 6, 0, 1, 2)

        self.scan_slm_mode = QtWidgets.QLabel("")
        self.scan_slm_mode.setWordWrap(True)
        self.scan_slm_mode.setStyleSheet("color: #c77800;")
        scan_layout.addWidget(self.scan_slm_mode, 7, 0, 1, 2)

        scan_group.setLayout(scan_layout)
        sidebar.addWidget(scan_group)



        # SLM preview
        sidebar.addWidget(QtWidgets.QLabel("SLM Preview:"))
        self.slm_preview = SLMPreviewWidget(self.slm, height=300)
        self.slm_preview.dragged_to.connect(self._on_preview_dragged)
        sidebar.addWidget(self.slm_preview)

        sidebar.addStretch()
        sidebar_scroll.setMinimumWidth(sidebar_widget.minimumSizeHint().width()
                                       + sidebar_scroll.verticalScrollBar().sizeHint().width())

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

        r = int(self.slm.spot_radius)
        for w in (self.radius_sb, self.radius_slider):
            w.blockSignals(True)
            w.setValue(max(self.RADIUS_MIN, min(self.RADIUS_MAX, r)))
            w.blockSignals(False)
        self.size_group.setEnabled(self.slm.mode == "spot" and not self._scanning)

        self.coord_label.setText(f"Center: ({cx}, {cy})")
        if self.slm.mode == "spot":
            self.size_label.setText(f"Radius: {self.slm.spot_radius}")
            self.extra_label.setText("Mode: Spot")
        else:
            self.size_label.setText(f"Size: {self.slm.grating_size}")
            self.extra_label.setText(f"Spacing: {self.slm.grating_spacing} | Angle: {self.slm.angle_deg}°")

        self.slm_preview.refresh()

    @QtCore.pyqtSlot(str, str)
    def _on_slm_link_changed(self, state, detail):
        self.slm_pill.set_state(state, detail, action="check the SLM server")

    def on_mode_changed(self):
        self.slm.set_mode("spot" if self.mode_spot_rb.isChecked() else "grating")

    def on_spot_radius_changed(self, value):
        self.slm.set_spot_radius(int(value))

    def on_apply_center(self):
        if self._scanning:
            return
        self.slm.set_center(self.center_x_sb.value(), self.center_y_sb.value())

    def on_reset_center(self):
        self.slm.reset_center_to_default()

    def _on_preview_dragged(self, cx, cy):
        if not self._scanning:
            self.slm.set_center(cx, cy)

    # Camera
    def _camera_connected(self):
        return not isinstance(self.camera, DummyCamera)

    def _on_camera_pill_clicked(self):
        if self._camera_connected():
            self.disconnect_camera()
        else:
            self.connect_camera()

    def connect_camera(self):
        """Open the Andor off the GUI thread; the andor button shows the result."""
        if self._camera_busy or self._camera_connected() or self._closing:
            return
        exposure_s = float(self.exposure_sb.value())
        gain = int(self.gain_sb.value())
        worker = self.worker
        self._camera_busy = "connecting"
        self._camera_error = ""
        self.cam_param_status.setText("Connecting to the Andor...")
        self._update_controls()

        def work():
            camera = AndorEMCCD(ExposureTime=exposure_s, gain=0.0, **andor_readout_params())
            reset_camera_state(camera, DummyCamera)
            # reset_camera_state zeroes the gain; bring the camera back to the panel
            _, msg = apply_camera_params(camera, DummyCamera, worker,
                                         exposure_s=exposure_s, gain=gain)
            return camera, msg

        BackgroundCall(work, self._on_camera_connected, self)

    def _on_camera_connected(self, result, error):
        self._camera_busy = ""
        if error is not None:
            self._camera_error = f"{type(error).__name__}: {error}"
            print(f"[camera] AndorEMCCD open failed ({error})")
            self.cam_param_status.setText(
                f"Andor not connected: {error}\n(Is liveOD holding it? Release it there, "
                f"then click the andor button.)")
            self._update_controls()
            return
        camera, msg = result
        if self._closing:
            camera.Close()
            return
        self.camera = camera
        self.worker.camera = camera
        self._camera_error = ""
        self.cam_param_status.setText(msg)
        # AndorEMCCD.__init__ opens the shutter
        self.shutter_btn.blockSignals(True)
        self.shutter_btn.setChecked(True)
        self.shutter_btn.blockSignals(False)
        self._update_controls()

    def disconnect_camera(self):
        """Release the Andor (e.g. for liveOD) without closing this window."""
        if self._camera_busy or not self._camera_connected() or self._scanning:
            return
        if self.worker.isRunning():
            self.worker.stop()
        camera = self.camera
        self._camera_busy = "disconnecting"
        self._update_controls()
        # AndorEMCCD.Close() closes the shutter before the SDK close (see liveOD's
        # CameraButton.close_camera for why it is Close, not close).
        BackgroundCall(camera.Close, self._on_camera_closed, self)

    def _on_camera_closed(self, _result, error):
        self._camera_busy = ""
        if error is not None:
            # Keep the live handle, as liveOD does, so the button still reports
            # the real device and a second click can try again.
            self._camera_error = f"close failed: {error}"
            print(f"[camera] {self._camera_error}")
            self._update_controls()
            return
        self.camera = DummyCamera()
        self.worker.camera = self.camera
        self._camera_error = ""
        self.cam_param_status.setText("Andor released. Click the andor button to connect again.")
        self._update_controls()

    def _render_camera_pill(self):
        connected = self._camera_connected()
        acquiring = connected and (self.worker.isRunning() or self._scanning)
        if self._camera_busy:
            state, detail = "loading", f"{self._camera_busy.capitalize()}..."
        elif self._camera_error:
            state, detail = "failed", self._camera_error
        elif acquiring:
            state, detail = "grabbing", "Scan running." if self._scanning else "Video running."
        elif connected:
            state, detail = "open", "Andor connected."
        else:
            state, detail = "closed", "Andor not connected."
        self.camera_pill.set_state(state, detail, action="disconnect" if connected else "connect")

    def _update_controls(self):
        """Enable what can be used now; the camera is shared by video, scan and connect."""
        self._render_camera_pill()
        ready = self._camera_connected() and not self._camera_busy
        for w in (self.video_btn, self.shutter_btn, self.apply_cam_btn):
            w.setEnabled(ready and not self._scanning)
        self.camera_pill.setEnabled(not self._camera_busy and not self._scanning)
        self.scan_btn.setEnabled(ready and not self._scanning)
        self.stop_scan_btn.setEnabled(self._scanning)
        for grp in self._pattern_groups:
            grp.setEnabled(not self._scanning)
        self.size_group.setEnabled(self.slm.mode == "spot" and not self._scanning)
        self.slm_preview.setEnabled(not self._scanning)
        self.stage_group.set_locked(self._scanning)

    def on_apply_camera_params(self):
        if not self._camera_connected():
            return
        ok, msg = apply_camera_params(
            self.camera, DummyCamera, self.worker,
            exposure_s=float(self.exposure_sb.value()),
            gain=int(self.gain_sb.value()),
        )
        self.cam_param_status.setText(msg)

    def toggle_video(self, checked):
        if checked and self._camera_connected():
            self.worker.start()
        else:
            self.video_btn.setChecked(False)
            self.worker.stop()
        self._update_controls()

    def _on_video_stopped(self):
        # Also fires when apply/shutter briefly stop and restart the video;
        # only a worker that is still stopped by now has really ended.
        if not self.worker.isRunning():
            self.video_btn.setChecked(False)
        self._update_controls()

    def toggle_shutter(self, checked):
        if not self._camera_connected():
            return
        mode = "open" if checked else "closed"
        was_running = self.worker.isRunning()
        if was_running:
            self.worker.stop()
        try:
            self.camera.setup_shutter(mode=mode)
        except Exception as e:
            print(e)
        if was_running:
            self.worker.start()

    @QtCore.pyqtSlot(np.ndarray)
    def update_camera_plot(self, data):
        self.cam_img_item.setImage(data.T, autoLevels=True)

    # Scan
    def start_scan(self):
        if self._scanning:
            return
        if not self._camera_connected() or self._camera_busy:
            self.scan_progress.setText("Connect the Andor first (andor button).")
            return
        if self.stage_group.position == POSITION_IN:
            answer = QtWidgets.QMessageBox.question(
                self, "APD stage is in",
                "The APD stage was last sent IN: the beamsplitter sends the light to "
                "the APD and the Andor is blocked.\n\nScan anyway? (Move Out in the "
                "APD Stage box clears the Andor.)")
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        R = int(self.scan_R_sb.value())
        step = int(self.scan_step_sb.value())

        x0, y0 = self.slm.get_center()
        xs, ys, points = scan_grid(x0, y0, R, step, self.slm.canvas_res)
        if not points:
            self.scan_progress.setText("Center is off canvas; nothing to scan.")
            return

        self._scan_start_center = (x0, y0)
        self._scan_picked = False
        self._scan_restore_pending = False
        self._scan_xs = xs
        self._scan_ys = ys
        nx, ny = len(xs), len(ys)

        # The scan owns the camera: it starts its own acquisition at every
        # position, so the free-running video has to stop for it.
        self._scan_was_running = self.worker.isRunning()
        if self._scan_was_running:
            self.worker.stop()

        self._scan_live = (self.preview_mode_cb.currentIndex() == 1)
        if self.scan_preview_dlg is not None:
            try:
                self.scan_preview_dlg.close()
            except Exception:
                pass
            self.scan_preview_dlg = None
        if self._scan_live:
            self.scan_preview_dlg = LiveScanPreviewDialog(
                nx, ny, xs, ys, parent=self, title=f"Scan Preview (live) ({ny}x{nx})"
            )
            self.scan_preview_dlg.spot_picked.connect(self.on_scan_spot_picked)
            self.scan_preview_dlg.finished.connect(lambda *_: self._maybe_return_to_start())
            self.scan_preview_dlg.show()

        # Find out afresh whether the SLM server confirms each pattern -- it
        # may have been restarted with a different run_server.py since.
        self.slm.reset_reply_probe()
        self.scan_slm_mode.setText("")

        self._scanning = True
        self._scan_total = len(points)
        self._scan_done = 0
        self._scan_last_t = time.monotonic()
        self.scan_progress.setText(f"Scanning 0/{len(points)} ...")
        self._update_controls()

        self.scan_worker = ScanWorker(
            self.slm, self.camera, points,
            settle_s=self.settle_sb.value() / 1000.0,
        )
        self.scan_worker.shot_sig.connect(self._on_scan_shot)
        self.scan_worker.finished_sig.connect(self._on_scan_finished)
        self.scan_worker.start()

    def _maybe_return_to_start(self):
        """Send the pattern back to where the scan started.

        No-op if the user left-clicked a tile (their pick stands), if the
        checkbox is off, or if there is no pending scan to return from.
        """
        if not self._scan_restore_pending:
            return
        self._scan_restore_pending = False
        if self._scan_picked or self._scan_start_center is None:
            return
        if self.return_to_start_cb.isChecked():
            self.slm.set_center(*self._scan_start_center)

    @QtCore.pyqtSlot(int, int)
    def on_scan_spot_picked(self, cx, cy):
        """Left-click on a scan tile -> move the pattern to that tile's position.

        Ignored while a scan is running: the ScanWorker owns the center then and
        would overwrite the pick at the next grid point.
        """
        if self._scanning:
            if self.scan_preview_dlg is not None:
                self.scan_preview_dlg.center_readout.setText(
                    "Scan still running -- click again once it finishes."
                )
            return
        self._scan_picked = True
        self._scan_restore_pending = False
        self.slm.set_center(int(cx), int(cy))

    def stop_scan(self):
        """
        Interrupt scan safely.
        Worker stops before the next position; the current one finishes.
        """
        if self._scanning and self.scan_worker is not None:
            self.scan_worker.stop()
            self.scan_progress.setText("Stopping after the current position...")
            self.stop_scan_btn.setEnabled(False)

    @QtCore.pyqtSlot(object)
    def _on_scan_shot(self, shot):
        self._scan_done += 1
        now = time.monotonic()
        step_s = now - self._scan_last_t
        self._scan_last_t = now

        if shot.frame is not None:
            self.cam_img_item.setImage(shot.frame.T, autoLevels=True)
        else:
            print(f"[scan] no frame at ({shot.point.cx}, {shot.point.cy}): {shot.error}")
        if self._scan_live and self.scan_preview_dlg is not None:
            try:
                self.scan_preview_dlg.update_tile(shot.point.row, shot.point.col, shot.frame)
            except Exception:
                pass

        if shot.slm_applied is None and not self.scan_slm_mode.text():
            self.scan_slm_mode.setText(
                "The SLM server does not confirm patterns (old run_server.py), so the "
                "settle time counts from the send and has to cover the server's own "
                "processing too. Restart the SLM server with the updated run_server.py "
                "for confirmed timing.")
        confirmed = {True: "SLM confirmed", None: "SLM unconfirmed"}.get(shot.slm_applied, "")
        applied = (f" (server {shot.server_apply_s * 1e3:.0f} ms)"
                   if shot.server_apply_s is not None else "")
        self.scan_progress.setText(
            f"Scanning {self._scan_done}/{self._scan_total}  |  {step_s:.2f} s/position  |  "
            f"{confirmed}{applied}")

    @QtCore.pyqtSlot(list, str)
    def _on_scan_finished(self, shots, outcome):
        self._scanning = False
        if self._closing:
            return

        nx, ny = len(self._scan_xs), len(self._scan_ys)
        n_missing = sum(1 for s in shots if s.frame is None)
        n_unconfirmed = sum(1 for s in shots if s.slm_applied is None)
        parts = [f"Scan {outcome}."]
        if n_missing:
            parts.append(f"{n_missing} position(s) have no frame (red X).")
        if len(shots) < self._scan_total:
            parts.append(f"{self._scan_total - len(shots)} position(s) not reached (blank).")
        if n_unconfirmed:
            parts.append(f"SLM application unconfirmed at {n_unconfirmed} position(s): "
                         f"old SLM server, settle {self.settle_sb.value()} ms from send.")
        summary = " ".join(parts)
        print(f"[scan] {summary}")
        self.scan_progress.setText(summary)

        if self._scan_was_running and self._camera_connected():
            self.video_btn.setChecked(True)
            self.worker.start()
        self._update_controls()

        # The scan leaves the pattern parked on the last grid point. Put it back
        # where the scan started -- but only once the preview is done with, and
        # only if the user did not left-click a tile to choose a position.
        self._scan_restore_pending = True

        if not self._scan_live:
            grid = shots_to_grid(shots, nx, ny)
            dlg = FinalScanPreviewDialog(grid, self._scan_xs, self._scan_ys, parent=self,
                                         title=f"Scan Preview ({ny}x{nx})", note=summary)
            dlg.spot_picked.connect(self.on_scan_spot_picked)
            dlg.exec()
            self._maybe_return_to_start()
        elif self.scan_preview_dlg is None or not self.scan_preview_dlg.isVisible():
            # live dialog already closed -> nothing left to click on
            self._maybe_return_to_start()
        else:
            self.scan_preview_dlg.set_note(summary)

    def closeEvent(self, event):
        self._closing = True
        try:
            if self.scan_worker is not None and self.scan_worker.isRunning():
                self.scan_worker.stop()
                # it finishes the position it is on (settle + one frame)
                self.scan_worker.wait(15000)
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


def andor_readout_params():
    """The vertical/horizontal shift settings this lab's Andor actually images with.

    AndorEMCCD.__init__ has its own defaults for these, but they are not the
    ones this camera is known to produce clean images at -- in particular it
    defaults to vs_amp=0 (normal vertical clock voltage). The values the
    experiment path images with are the AndorParams defaults, which reach the
    camera through CameraNanny.open(); read them from there so this GUI and the
    experiment stay on one set of numbers instead of drifting apart.

    AndorParams is imported straight from waxx rather than through
    kexp.config.camera_id because that module pulls in the kexp package root,
    and so artiq -- a heavy import to hang a preview GUI on. kexp's camera_id
    does not override any of these four, so the values are the same either way.
    """
    # 2026-09-23: vs_speed/vs_amp are set in kexp.config.camera_id, so the
    # kexp values are tried first and the bare waxx defaults second.
    # fallback = dict(hs_speed=0, vs_speed=0, vs_amp=0, preamp=2) # 2026-09-23; reverted, run 80708
    #   (0.3 us / Normal transfers no charge: the light frames are blank)
    fallback = dict(hs_speed=0, vs_speed=1, vs_amp=3, preamp=2) # restored 2026-09-24
    try:
        try:
            from kexp.config.camera_id import camera_frame
            p = camera_frame().andor
        except Exception as e:
            print(f"[camera] kexp camera_id unavailable ({e}); using waxx AndorParams defaults")
            from waxx.control.cameras.camera_param_classes import AndorParams
            p = AndorParams()
        params = dict(
            hs_speed=int(p.hs_speed),
            vs_speed=int(p.vs_speed),
            vs_amp=int(p.vs_amp),
            preamp=int(p.preamp),
        )
        print(f"[camera] readout params from AndorParams: {params}")
        return params
    except Exception as e:
        print(f"[camera] could not read AndorParams ({e}); "
              f"using known-good fallback {fallback}")
        return fallback


class UnifiedExperiment():
    def build(self):
        # The window opens the Andor itself, off the GUI thread, and can release
        # and re-open it later (andor button) without being closed.
        self.camera = None

    def run(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        gui = UnifiedControlGUI(self.camera)
        gui.show()
        app.exec()

if __name__ == "__main__":
    ue = UnifiedExperiment()
    ue.build()
    ue.run()
