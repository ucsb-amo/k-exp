import argparse
import sys
import time
import numpy as np
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg

from waxx.control import AndorEMCCD

from frame_source import LocalAndorSource, SourceChoice, choose_source
try:
    # The Andor opened here goes through beacon's camera server logic, so that
    # liveOD's camera host can take it over (served_source).
    from served_source import (ServedAndorSource, DEFAULT_ANDOR_CAMERA_ID, describe_holder,
                               handover_text, is_lent_error, liveod_camera_id, trigger_summary)
    _SERVED_ERROR = ""
except ImportError as _e:       # no beacon here: the Andor is opened straight through the SDK
    ServedAndorSource = None
    _SERVED_ERROR = f"{type(_e).__name__}: {_e}"

    def trigger_summary(report):
        return str(report)
try:
    # Frames on ARTIQ TTL edges: a precompiled pulse kernel on the Andor's
    # trigger line (artiq_trigger); kexp's tables are read when it is made.
    from artiq_trigger import make_andor_trigger
    _TRIGGER_ERROR = ""
except ImportError as _e:
    make_andor_trigger = None
    _TRIGGER_ERROR = f"{type(_e).__name__}: {_e}"
from run_gate import RunGate, CombinedGate
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
    GATE_REFRESH_MS = 250

    # frames and video-stopped notices, re-emitted from the source's thread
    _frame_sig = QtCore.pyqtSignal(np.ndarray)
    _video_stopped_sig = QtCore.pyqtSignal()
    # the Andor served here was taken over by liveOD / given back (info dict),
    # re-emitted from its server's thread
    _handover_sig = QtCore.pyqtSignal(object)
    _returned_sig = QtCore.pyqtSignal(object)

    def __init__(self, camera=None, connect_camera_on_start=True, source=None, run_gate=None,
                 source_mode="auto", directory=None):
        """``source``: a FrameSource, used as given. None: the Andor opened
        here -- LocalAndorSource on ``camera`` when a camera object is given
        (tests), else a ServedAndorSource (beacon's camera server logic, so
        liveOD's camera host can take it over; LocalAndorSource if beacon is
        missing), opened by the andor button / on start. Unless
        ``source_mode="direct"`` or a camera is given, the window first looks
        for liveOD's Andor (choose_source, off the GUI thread, through
        ``directory``; None: UDP discovery) and opens nothing until that is
        settled: "auto" takes liveOD's Andor when a camera host serves it and
        falls back to the Andor opened here with a banner; "stream" takes
        liveOD's Andor or nothing. When liveOD takes over the Andor opened
        here, the window follows it to liveOD's camera host (not with
        --direct). ``run_gate``: a RunGate, or any callable returning
        ``(ok, reason)``. None polls liveOD's run state (RunGate's default)."""
        super().__init__()
        self.setWindowTitle("SLM Andor preview")
        self.resize(1500, 900)
        self._closing = False

        # Camera, through a FrameSource only. The local one keeps a
        # DummyCamera while the Andor is not connected; the andor button
        # connects and releases it without closing the window.
        built_local = source is None
        self._source_mode = source_mode
        self._directory = directory
        self._connect_on_start = bool(connect_camera_on_start)
        # No camera given and not --direct: find out first whether liveOD
        # serves the Andor. Until then the local source below is a placeholder
        # that nothing opens.
        self._source_pending = built_local and camera is None and source_mode != "direct"
        self._source_refused = ""   # why no camera may be connected (--stream, none served)
        self._src_seen = (0, 0)     # the source's (runs_seen, restarts_seen) acted on
        self._video_note = ""
        if built_local:
            source = self._make_own_source(camera)
        self.source = source
        # The Andor served here (ServedAndorSource), kept after liveOD takes it
        # over so that its server is shut down with the window.
        self._own_source = source if getattr(source, "kind", "") == "served" else None
        self._handover_pending = None   # a handover that came during a scan
        self._after_handover = False    # following the Andor to liveOD's camera host
        self._resume_video = False      # restart the video once attached there
        self._handover_sig.connect(self._on_handover)
        self._returned_sig.connect(self._on_returned)
        if self._own_source is not None:
            # called on its server's threads: re-emitted to this one
            self._own_source.on_handover = self._handover_sig.emit
            self._own_source.on_returned = self._returned_sig.emit
        # This window's view of the connection. It changes on the GUI thread,
        # when a connect or release lands, together with the busy flag -- the
        # source itself switches earlier, on the thread doing the open/close.
        self._connected = self.source.is_open()
        self._camera = getattr(self.source, "camera", None)
        # "finding" / "connecting" / "disconnecting" while under way
        self._camera_busy = ""
        self._camera_error = ""
        self._frame_sig.connect(self.update_camera_plot)
        self._video_stopped_sig.connect(self._on_video_stopped)

        # Run gate: no SLM write while a run is in progress, or while that is
        # not known (liveOD unreachable or slow). Fails closed until the
        # first answer.
        self._owns_gate = run_gate is None
        self.run_gate = run_gate if run_gate is not None else RunGate()
        # What the SLM controller and the scan ask: the run gate, and the
        # camera source's own view (liveOD's camera host says when a run holds
        # its Andor, or when it restarted or stopped answering).
        self.write_gate = CombinedGate(self.run_gate, lambda: self.source)
        self._gate_open = False
        self._gate_reason = "run state not checked yet -- SLM writes blocked"
        self._gate_runs_seen = 0
        self._gate_was_reachable = False
        self._gate_lost = False

        # SLM
        self.slm = SLMController(canvas_res=(1920, 1200), server_ip="192.168.1.102",
                                 server_port=5000, write_gate=self.write_gate)
        self.slm.state_changed.connect(self._on_slm_state_changed)
        self.slm.link_changed.connect(self._on_slm_link_changed)
        self.slm.blocked.connect(self._on_slm_blocked)
        self.slm.sync_changed.connect(self._on_slm_sync_changed)

        # Scan
        self.scan_worker = None
        self.scan_preview_dlg = None
        self._scanning = False
        self._scan_stopping = False
        self._scan_live = False
        self._scan_was_running = False
        self._scan_xs = []
        self._scan_ys = []
        self._scan_total = 0
        self._scan_done = 0
        self._scan_last_t = None
        self._scan_start_center = None

        # ARTIQ trigger (frames on TTL edges; the Camera Control tick box).
        # The pulser is made when the box is first ticked, off the GUI thread
        # (it reads kexp's tables and the device db); the source gets it
        # whenever it can take triggered frames.
        self._pulser = None
        self._pulser_error = ""
        self._pulser_loading = False
        self._trigger_testing = False
        self._trigger_test_video = False

        self.init_ui()
        if built_local and self._camera_connected():
            self.source.reset_to_video()
        if built_local and camera is None and source_mode == "direct":
            choice = choose_source("direct")
            self._set_source_banner(self._direct_banner(choice.banner), choice.level)
        self._on_slm_state_changed()
        # This window's pattern is on the SLM only once it has sent it.
        self.slm.mark_unknown("SLM state unknown -- not written from this window yet")
        self._render_gate_banner()
        self._update_controls()

        start_gate = getattr(self.run_gate, "start", None)
        if start_gate is not None:
            start_gate()
        self._gate_timer = QtCore.QTimer(self)
        self._gate_timer.setInterval(self.GATE_REFRESH_MS)
        self._gate_timer.timeout.connect(self._refresh_gate)
        self._gate_timer.start()

        self.slm.check_link()
        # Connecting reads the stage position; it never moves the stage.
        QtCore.QTimer.singleShot(0, self.stage_group.connect_stage)
        if self._source_pending:
            # connects (connect_camera_on_start) once the source is settled
            self._find_source()
        elif connect_camera_on_start and not self._camera_connected():
            QtCore.QTimer.singleShot(0, self.connect_camera)

    @property
    def camera(self):
        """The camera object behind a local source, as this window last saw it
        (None for other sources)."""
        return self._camera

    def _make_own_source(self, camera):
        """The source for the Andor this window opens itself: served through
        beacon's camera server logic, so liveOD's camera host can take it over
        (ServedAndorSource) -- or LocalAndorSource on a camera object handed in
        (tests), and when beacon is missing."""
        if camera is None and ServedAndorSource is not None:
            return make_own_andor_source()
        if camera is None:
            print(f"[camera] the Andor is opened straight through the SDK ({_SERVED_ERROR}): "
                  f"liveOD's camera host cannot take it over; release it here when liveOD "
                  f"needs it")
        return LocalAndorSource(camera, open_camera=open_local_andor)

    def _direct_banner(self, banner):
        """A "direct" choice's banner, and what liveOD may do with the Andor opened here."""
        own = self._own_source
        if own is None:
            return banner
        then = ("the spot finder then stops using it" if self._source_mode == "direct" else
                "the spot finder then follows it there")
        return (f"{banner.rstrip('.')}. It is served as {own.server_id}: liveOD's camera host "
                f"can take it over when it needs it, and {then}.")


    def on_apply_pattern_params(self):
        if self.slm.mode == "spot":
            self.slm.set_spot_radius(self.radius_sb.value())
        else:
            self.slm.set_grating_size(self.grating_size_sb.value())
            self.slm.set_grating_spacing(self.grating_spacing_sb.value())
            self.slm.set_angle_deg(self.angle_sb.value())

    def keyPressEvent(self, event):
        # The scan owns the pattern while it runs; a nudge now would put the
        # next frame at a position other than the one it is filed under. And
        # nothing moves it while the run gate is closed (the banner says why).
        if self._scanning or not self._gate_open:
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

        # Run gate: shown only while SLM writes are blocked, and why.
        self.run_banner = QtWidgets.QLabel("")
        self.run_banner.setWordWrap(True)
        self.run_banner.setStyleSheet(
            "background-color: #c62828; color: white; font-weight: bold; "
            "padding: 4px; border-radius: 4px;")
        self.run_banner.setVisible(False)
        sidebar.addWidget(self.run_banner)

        # Where the camera frames come from: liveOD's Andor, or the camera
        # opened here (and why).
        self.source_banner = QtWidgets.QLabel("")
        self.source_banner.setWordWrap(True)
        self.source_banner.setVisible(False)
        sidebar.addWidget(self.source_banner)

        # Shown while what the SLM displays is not known to be this window's
        # pattern (a run may have written it). Re-send only on a click.
        self.slm_sync_row = QtWidgets.QWidget()
        sync_row = QtWidgets.QHBoxLayout(self.slm_sync_row)
        sync_row.setContentsMargins(0, 0, 0, 0)
        self.slm_sync_label = QtWidgets.QLabel("")
        self.slm_sync_label.setWordWrap(True)
        self.slm_sync_label.setStyleSheet("color: #c77800;")
        sync_row.addWidget(self.slm_sync_label, 1)
        self.resend_btn = QtWidgets.QPushButton("Re-send")
        self.resend_btn.setToolTip(
            "Send this window's pattern to the SLM again. Never done automatically; "
            "blocked while a run is in progress.")
        self.resend_btn.clicked.connect(self.on_resend)
        sync_row.addWidget(self.resend_btn)
        self.slm_sync_row.setVisible(False)
        sidebar.addWidget(self.slm_sync_row)

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

        # Frames on ARTIQ TTL edges (served_source, triggered scans): the scan
        # arms the Andor once and pulses its trigger line once per frame.
        self.trigger_cb = QtWidgets.QCheckBox("Trigger frames from ARTIQ")
        self.trigger_cb.setToolTip(
            "Scan frames exposed on TTL edges fired from ARTIQ on the Andor's trigger line "
            "(cameras.andor.trigger_ttl), as a run exposes them: the camera is armed once for "
            "the scan (external trigger) and one precompiled core.reset + pulse kernel runs per "
            "frame.\nThe scan takes the ARTIQ core from the monitor for its duration "
            "(composite ops are fenced, the device state reads UNTRUSTED meanwhile) and the "
            "monitor is restarted after it when no run is starting.\nNeeds the Andor opened "
            "here, not liveOD's.")
        self.trigger_cb.toggled.connect(self._on_trigger_toggled)
        cam_layout.addWidget(self.trigger_cb)

        self.trigger_test_btn = QtWidgets.QPushButton("Test trigger (one frame)")
        self.trigger_test_btn.setToolTip(
            "Arm the Andor for external triggers, fire one pulse from ARTIQ, show the frame "
            "it exposed, disarm.")
        self.trigger_test_btn.clicked.connect(self.on_test_trigger)
        cam_layout.addWidget(self.trigger_test_btn)

        self.trigger_status = QtWidgets.QLabel("")
        self.trigger_status.setWordWrap(True)
        self.trigger_status.setStyleSheet("color: gray;")
        self.trigger_status.setVisible(False)
        cam_layout.addWidget(self.trigger_status)

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

        # Not automatic: a write deferred to "after the preview closes" could
        # land in the middle of a run.
        self.return_btn = QtWidgets.QPushButton("Return now")
        self.return_btn.setToolTip(
            "Send the pattern back to where the last scan started. Only on this "
            "click, and only while no run is in progress.")
        self.return_btn.clicked.connect(self.on_return_to_start)
        scan_layout.addWidget(self.return_btn, 4, 0, 1, 2)

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
        self.size_group.setEnabled(self.slm.mode == "spot" and self._can_write_pattern())

        # the radio buttons too, so a refused mode change does not stay ticked
        for rb in (self.mode_spot_rb, self.mode_grating_rb):
            rb.blockSignals(True)
        (self.mode_spot_rb if self.slm.mode == "spot" else self.mode_grating_rb).setChecked(True)
        for rb in (self.mode_spot_rb, self.mode_grating_rb):
            rb.blockSignals(False)

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

    @QtCore.pyqtSlot(str)
    def _on_slm_blocked(self, reason):
        # The controller changed nothing; put the widgets back to its state.
        self._on_slm_state_changed()
        self.statusBar().showMessage(f"SLM not written: {reason}", 8000)
        self._refresh_gate()

    @QtCore.pyqtSlot(str)
    def _on_slm_sync_changed(self, reason):
        self.slm_sync_label.setText(reason)
        self.slm_sync_row.setVisible(bool(reason))

    def on_resend(self):
        if self._scanning:
            return
        self.slm.resend()

    # Run gate
    def _can_write_pattern(self):
        return self._gate_open and not self._scanning

    def _refresh_gate(self):
        """Read the write gate; update the banner, the controls and the SLM state line."""
        snap = self.write_gate.snapshot()
        ok, reason, state = bool(snap["ok"]), snap.get("reason", ""), snap.get("state")

        # liveOD was unreachable and answers again: a run could have come and
        # gone unseen in between.
        if state == "unreachable":
            self._gate_lost = self._gate_lost or self._gate_was_reachable
        elif state is not None:
            self._gate_was_reachable = True
            if self._gate_lost:
                self._gate_lost = False
                self.slm.mark_unknown(
                    "SLM state unknown -- liveOD was unreachable, so a run may have written it")
        # A run seen (starting, or come and gone between polls). Its kernel
        # may write the SLM (setup_slm), so what the SLM shows is not known.
        runs_seen = snap.get("runs_seen")
        if runs_seen is not None and runs_seen != self._gate_runs_seen:
            self._gate_runs_seen = runs_seen
            rid = snap.get("last_run_id")
            who = f"run {rid}" if rid else "a run"
            self.slm.mark_unknown(f"SLM state unknown -- {who} may have written it")
        # liveOD's camera host (a StreamSource): a run took its Andor, or the
        # host restarted -- either may have left another pattern on the SLM.
        src = snap.get("source")
        if src:
            seen = (int(src.get("runs_seen") or 0), int(src.get("restarts_seen") or 0))
            if seen != self._src_seen:
                new_runs = seen[0] > self._src_seen[0]
                new_restarts = seen[1] > self._src_seen[1]
                self._src_seen = seen
                if new_restarts:
                    self.slm.mark_unknown("SLM state unknown -- liveOD's camera host "
                                          "restarted, so a run may have written it")
                elif new_runs:
                    tag = src.get("last_run_tag")
                    who = f"run {tag}" if tag else "a run"
                    self.slm.mark_unknown(f"SLM state unknown -- {who} took liveOD's Andor "
                                          f"and may have written it")

        if (ok, reason) != (self._gate_open, self._gate_reason):
            self._gate_open, self._gate_reason = ok, reason
            self._render_gate_banner()
            self._update_controls()
        self._refresh_video_note()

    def _refresh_video_note(self):
        """Say in the status bar why a running video shows nothing (StreamSource)."""
        note_fn = getattr(self.source, "video_note", None)
        note = note_fn() if note_fn is not None else ""
        if note == self._video_note:
            return
        old, self._video_note = self._video_note, note
        bar = self.statusBar()
        if note:
            bar.showMessage(note)
        elif old and bar.currentMessage() == old:
            bar.clearMessage()

    _BANNER_COLORS = {"info": "#1565c0", "warn": "#ef6c00", "error": "#c62828"}

    def _set_source_banner(self, text, level="info"):
        color = self._BANNER_COLORS.get(level, self._BANNER_COLORS["info"])
        self.source_banner.setStyleSheet(
            f"background-color: {color}; color: white; padding: 4px; border-radius: 4px;")
        if text and not text.startswith("liveOD"):     # "liveOD" keeps its spelling
            text = text[:1].upper() + text[1:]
        self.source_banner.setText(text)
        self.source_banner.setVisible(bool(text))

    def _render_gate_banner(self):
        if self._gate_open:
            self.run_banner.setVisible(False)
            return
        text = self._gate_reason or "SLM writes blocked"
        self.run_banner.setText(text[:1].upper() + text[1:])
        self.run_banner.setVisible(True)

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
        return self._connected

    def _shared_source(self):
        """True when the camera belongs to liveOD (StreamSource), not to this window."""
        return bool(getattr(self.source, "shared", False))

    def _find_source(self, mode=None):
        """Look for liveOD's Andor off the GUI thread (bounded, a few seconds).

        Nothing opens a camera until the answer is in: then liveOD's Andor, or
        the Andor opened here with a banner saying why, or (--stream, or after
        liveOD took the Andor over: ``mode="stream"``) none."""
        self._source_pending = True
        self._source_refused = ""
        self._camera_busy = "finding"
        self._camera_error = ""
        self.cam_param_status.setText("Looking for liveOD's camera host...")
        self._update_controls()
        mode, directory = mode or self._source_mode, self._directory
        BackgroundCall(lambda: choose_source(mode, directory), self._on_source_chosen, self)

    def _on_source_chosen(self, choice, error):
        self._camera_busy = ""
        self._source_pending = False
        after = self._after_handover
        if error is not None:       # choose_source reports the lookup's own errors
            why = f"looking for liveOD's camera host failed ({type(error).__name__}: {error})"
            choice = (SourceChoice("none", f"{why} -- --stream was given, so the Andor is not "
                                           f"opened directly", "error")
                      if self._source_mode == "stream" or after else
                      SourceChoice("direct", f"{why} -- using the camera directly; release it "
                                             f"in liveOD first", "warn"))
        if self._closing:
            return
        banner = choice.banner
        if choice.kind == "stream":
            self.source = choice.source
            self._connected = self.source.is_open()
            self._camera = None
            self._src_seen = (0, 0)
            if after:
                banner = (f"liveOD's camera host took the Andor over; following it there "
                          f"({choice.source.description}): liveOD keeps the camera and its "
                          f"settings; a run takes it")
        elif after:
            # liveOD has the Andor, and its camera host cannot be found now
            banner = (f"liveOD's camera host took the Andor over, but it cannot be found now "
                      f"({banner}); click the andor button to look again")
        elif choice.kind == "direct":
            banner = self._direct_banner(banner)
        self._source_refused = banner if choice.kind == "none" else ""
        print(f"[camera] source: {choice.kind} -- {banner}")
        self._set_source_banner(banner, choice.level)
        self.cam_param_status.setText("")
        self._apply_trigger_to_source()
        self._render_trigger_status()
        self._update_controls()
        if (self._connect_on_start or after) and not self._source_refused:
            self.connect_camera()

    def _on_camera_pill_clicked(self):
        if self._source_refused:
            # --stream and nothing served, or liveOD took the Andor over and
            # its camera host was not found: look again (for liveOD's only)
            self._find_source("stream" if self._after_handover else None)
        elif self._camera_connected():
            self.disconnect_camera()
        else:
            self.connect_camera()

    def _set_shutter_button(self, checked):
        self.shutter_btn.blockSignals(True)
        self.shutter_btn.setChecked(bool(checked))
        self.shutter_btn.blockSignals(False)

    def connect_camera(self):
        """Open the Andor (or attach to liveOD's) off the GUI thread; the andor
        button shows the result."""
        if self._camera_busy or self._camera_connected() or self._closing:
            return
        if self._source_pending:
            return
        if self._source_refused:
            self.cam_param_status.setText(self._source_refused)
            return
        exposure_s = float(self.exposure_sb.value())
        gain = int(self.gain_sb.value())
        source = self.source
        shared = self._shared_source()
        self._camera_busy = "attaching" if shared else "connecting"
        self._camera_error = ""
        self.cam_param_status.setText("Attaching to liveOD's Andor..." if shared
                                      else "Connecting to the Andor...")
        self._update_controls()

        def work():
            source.open()
            if shared:
                # liveOD owns the camera's settings: show them, don't overwrite them
                return "adopt", source.panel_settings()
            # the local source resets to video (zeroes the gain): bring the
            # camera back to the panel
            _, msg = source.apply(exposure_s, gain)
            return "applied", msg

        BackgroundCall(work, self._on_camera_connected, self)

    def _on_camera_connected(self, result, error):
        self._camera_busy = ""
        shared = self._shared_source()
        if (error is not None and self._own_source is not None
                and self.source is self._own_source and is_lent_error(error)):
            # liveOD took the Andor over earlier and still has it
            self._connected = self.source.is_open()
            self._update_controls()
            self._on_handover({"holder": getattr(error, "holder", None) or {}, "ok": True,
                               "already": True, "video": False})
            return
        if error is not None:
            # open() may have succeeded and the apply after it failed
            self._connected = self.source.is_open()
            self._camera = getattr(self.source, "camera", None)
            self._camera_error = f"{type(error).__name__}: {error}"
            if shared:
                print(f"[camera] attaching to liveOD's Andor failed ({error})")
                self.cam_param_status.setText(
                    f"liveOD's Andor not attached: {error}\n(Is liveOD running, with its "
                    f"camera host? Click the andor button to try again.)")
            else:
                print(f"[camera] AndorEMCCD open failed ({error})")
                self.cam_param_status.setText(
                    f"Andor not connected: {error}\n(Is liveOD holding it? Release it there, "
                    f"then click the andor button.)")
            self._update_controls()
            return
        kind, value = result
        if self._closing:
            try:
                self.source.close()
            except Exception as e:
                print(f"[camera] close after a late connect failed: {e}")
            return
        self._connected = True
        self._camera = getattr(self.source, "camera", None)
        self._camera_error = ""
        self._apply_trigger_to_source()
        self._render_trigger_status()
        if kind == "adopt":
            self._show_panel_settings(value)
        else:
            self.cam_param_status.setText(value)
            # AndorEMCCD.__init__ opens the shutter (ServedAndorSource opens it too)
            self._set_shutter_button(True)
        self._update_controls()
        if self._resume_video:
            # the video was running when liveOD took the Andor over: go on
            # with liveOD's (its camera host may refuse the stream during a
            # run; the status bar then says why)
            self._resume_video = False
            self.video_btn.setChecked(True)
            self._start_video()
            self._update_controls()

    def _show_panel_settings(self, ps):
        """Put liveOD's live settings in the panel, and say what they are."""
        exp, gain, shutter = ps.get("exposure_s"), ps.get("gain"), ps.get("shutter_open")
        if exp is not None:
            self.exposure_sb.setValue(exp)
        if gain is not None:
            self.gain_sb.setValue(gain)
        if shutter is not None:
            self._set_shutter_button(shutter)
        exp_txt = f"{exp:.4f} s" if exp is not None else "unknown"
        text = (f"Attached to liveOD's Andor (settings rev {ps.get('settings_rev')}): exposure "
                f"{exp_txt}, EM gain {gain if gain is not None else 'unknown'}, shutter "
                f"{'open' if shutter else 'closed' if shutter is not None else 'unknown'}. "
                f"These are liveOD's live settings: Apply changes them for liveOD's live "
                f"view too; runs use their own.")
        if gain is not None and gain > self.gain_sb.maximum():
            text += f" (EM gain {gain} is above this panel's limit of {self.gain_sb.maximum()}.)"
        self.cam_param_status.setText(text)

    def disconnect_camera(self):
        """Release the Andor (e.g. for liveOD) without closing this window;
        from liveOD's Andor, detach (liveOD keeps the camera)."""
        if self._camera_busy or not self._camera_connected() or self._scanning:
            return
        if self.source.video_running():
            self.source.stop_video()
        self._camera_busy = "detaching" if self._shared_source() else "disconnecting"
        self._update_controls()
        # The local source closes with AndorEMCCD.Close(), which closes the
        # shutter before the SDK close; a stream source only detaches.
        BackgroundCall(self.source.close, self._on_camera_closed, self)

    def _on_camera_closed(self, _result, error):
        self._camera_busy = ""
        if error is not None:
            # Keep the live handle, as liveOD does, so the button still reports
            # the real device and a second click can try again.
            self._camera_error = f"close failed: {error}"
            print(f"[camera] {self._camera_error}")
            self._update_controls()
            return
        self._connected = False
        self._camera = getattr(self.source, "camera", None)
        self._camera_error = ""
        text = ("Detached from liveOD's Andor (liveOD keeps it). Click the andor button to "
                "attach again." if self._shared_source() else
                "Andor released. Click the andor button to connect again.")
        # ServedAndorSource.close() returns the camera's close report
        failed = list(getattr(_result, "errors", None) or ())
        if failed or getattr(_result, "attached_after", False):
            text += (f" The close reported: device still attached="
                     f"{getattr(_result, 'attached_after', None)}, failed steps: "
                     f"{'; '.join(map(str, failed)) or 'none'}.")
        self.cam_param_status.setText(text)
        self._update_controls()

    def _on_handover(self, info):
        """liveOD's camera host took over the Andor served here: it was closed
        here first (video stopped, shutter closed, SDK released) and liveOD
        opened it. Follow it to liveOD's camera host -- not with --direct."""
        if self._closing:
            return
        if self._scanning:
            # the scan stops at its snap (Preempted), filing nothing there;
            # then this goes on (_on_scan_finished)
            self._handover_pending = info
            return
        own = self._own_source
        text = handover_text(info)
        if self.source is own:
            self._connected = own.is_open()
            self._camera = None
            self._resume_video = self._resume_video or bool(info.get("video"))
            self.video_btn.setChecked(False)
        print(f"[camera] {text}")
        self.statusBar().showMessage(text, 15000)
        self.cam_param_status.setText(text + ".")
        if self._source_mode == "direct":
            self._resume_video = False
            self._set_source_banner(
                f"{text}. --direct: the spot finder does not follow it to liveOD's camera host; "
                f"click the andor button to open it here again once liveOD has given it back.",
                "warn")
            self._update_controls()
            return
        if self.source is not own:
            self._update_controls()     # already following liveOD (a late notice)
            return
        self._after_handover = True
        self._set_source_banner(f"{text}; attaching to liveOD's Andor...", "info")
        self._find_source("stream")

    def _on_returned(self, info):
        """liveOD gave the Andor served here back (it closed its own)."""
        if self._closing or self.source is not self._own_source:
            return              # following liveOD's camera host: nothing changes here
        text = (f"{describe_holder(info.get('holder'))} gave the Andor back; click the andor "
                f"button to open it here again")
        print(f"[camera] {text}")
        self._set_source_banner(text, "info")
        self.cam_param_status.setText(text + ".")
        self._update_controls()

    def _render_camera_pill(self):
        connected = self._camera_connected()
        shared = self._shared_source()
        acquiring = connected and (self.source.video_running() or self._scanning)
        if self._camera_busy == "finding":
            state, detail = "loading", "Looking for liveOD's camera host (a few seconds)..."
        elif self._camera_busy:
            state, detail = "loading", f"{self._camera_busy.capitalize()}..."
        elif self._source_refused:
            state, detail = "failed", self._source_refused
        elif self._camera_error:
            state, detail = "failed", self._camera_error
        elif acquiring:
            state = "grabbing"
            detail = "Scan running." if self._scanning else "Video running."
            if shared:
                detail += " Frames from liveOD's Andor."
        elif connected:
            state = "open"
            served = getattr(self.source, "server_id", "") if not shared else ""
            detail = (f"Attached to liveOD's Andor ({getattr(self.source, 'description', '')});"
                      f" liveOD keeps the camera." if shared else
                      f"Andor connected, served as {served}: liveOD's camera host can take it "
                      f"over." if served else "Andor connected.")
        else:
            state = "closed"
            lent = getattr(self.source, "lent_to", lambda: None)() if not shared else None
            detail = ("liveOD's Andor not attached." if shared else
                      f"Andor taken over by {describe_holder(lent)}." if lent else
                      "Andor not connected.")
        if self._source_refused:
            action = "look for liveOD's camera host again"
        elif shared:
            action = "detach" if connected else "attach"
        else:
            action = "disconnect" if connected else "connect"
        self.camera_pill.set_state(state, detail, action=action)

    def _update_controls(self):
        """Enable what can be used now; the camera is shared by video, scan and connect."""
        self._render_camera_pill()
        ready = self._camera_connected() and not self._camera_busy
        busy = self._scanning or self._trigger_testing
        for w in (self.video_btn, self.shutter_btn, self.apply_cam_btn):
            w.setEnabled(ready and not busy)
        self.camera_pill.setEnabled(not self._camera_busy and not busy)
        # the ARTIQ trigger: the tick box whenever the camera is not in use;
        # the test button only when a triggered frame could be taken now (it
        # takes the core, so never while a run may be going: the gate says)
        self.trigger_cb.setEnabled(not busy)
        self.trigger_test_btn.setEnabled(ready and not busy and self._trigger_wanted()
                                         and not self._trigger_refusal() and self._gate_open)
        # Everything that writes the SLM: never while a scan owns the pattern,
        # never while the run gate is closed.
        can_write = self._can_write_pattern()
        self.scan_btn.setEnabled(ready and can_write)
        self.stop_scan_btn.setEnabled(self._scanning and not self._scan_stopping)
        for grp in self._pattern_groups:
            grp.setEnabled(can_write)
        self.size_group.setEnabled(self.slm.mode == "spot" and can_write)
        self.slm_preview.setEnabled(can_write)
        self.return_btn.setEnabled(can_write and self._scan_start_center is not None)
        self.resend_btn.setEnabled(can_write)
        self.stage_group.set_locked(self._scanning)

    def _async_source(self):
        """Camera requests go off the GUI thread: to liveOD's camera host
        (StreamSource), or to the worker of the Andor served here (ServedAndorSource)."""
        return self._shared_source() or bool(getattr(self.source, "async_ops", False))

    def on_apply_camera_params(self):
        if not self._camera_connected():
            return
        exposure_s, gain = float(self.exposure_sb.value()), int(self.gain_sb.value())
        if self._async_source():
            # a request to liveOD's camera host, or to the camera's worker: off the GUI thread
            self.cam_param_status.setText("Applying to liveOD's Andor..." if self._shared_source()
                                          else "Applying...")
            source = self.source
            BackgroundCall(lambda: source.apply(exposure_s, gain), self._on_params_applied, self)
            return
        ok, msg = self.source.apply(exposure_s, gain)
        self.cam_param_status.setText(msg)

    def _on_params_applied(self, result, error):
        self.cam_param_status.setText(
            f"Not applied: {type(error).__name__}: {error}" if error is not None else result[1])

    def _start_video(self):
        # emitting a signal is safe from the source's thread; the slots run here
        self.source.start_video(self._frame_sig.emit, self._video_stopped_sig.emit)

    def toggle_video(self, checked):
        if checked and self._camera_connected():
            self._start_video()
        else:
            self.video_btn.setChecked(False)
            self.source.stop_video()
        self._update_controls()

    def _on_video_stopped(self):
        # Also fires when apply/shutter briefly stop and restart the video;
        # only a source whose video is still stopped by now has really ended.
        if not self.source.video_running():
            self.video_btn.setChecked(False)
            # e.g. a run took liveOD's Andor (StreamSource); not restarted by itself
            why = getattr(self.source, "video_stop_reason", "")
            if why:
                self.statusBar().showMessage(why, 10000)
        self._update_controls()

    def toggle_shutter(self, checked):
        if not self._camera_connected():
            return
        if self._async_source():
            # (ok, msg) from liveOD's camera host or the camera's worker, off the
            # GUI thread; the button goes back if it was refused
            source, want = self.source, bool(checked)

            def done(result, error):
                ok, msg = ((False, f"Shutter not set: {type(error).__name__}: {error}")
                           if error is not None else result)
                self.cam_param_status.setText(msg)
                if not ok:
                    self._set_shutter_button(not want)

            BackgroundCall(lambda: source.set_shutter(want), done, self)
            return
        self.source.set_shutter(bool(checked))

    @QtCore.pyqtSlot(np.ndarray)
    def update_camera_plot(self, data):
        self.cam_img_item.setImage(data.T, autoLevels=True)

    # ARTIQ trigger
    def _trigger_wanted(self):
        return bool(self.trigger_cb.isChecked())

    def _trigger_refusal(self):
        """Why triggered frames cannot be taken now; "" when they can."""
        if not self._trigger_wanted():
            return ""
        if self._pulser_loading:
            return "the ARTIQ trigger is still being set up"
        if self._pulser_error:
            return self._pulser_error
        if self._pulser is None:
            return "the ARTIQ trigger is not set up"
        if not getattr(self.source, "supports_trigger", False):
            return (getattr(self.source, "trigger_refusal", "")
                    or "this camera source takes no triggered frames")
        return ""

    def _trigger_run_check(self):
        """Asked by the pulser, before it restarts the monitor, whether a run
        is going as far as liveOD says: one fresh POLL, failing closed.  Called
        on the scan's thread."""
        gate = self.run_gate
        poll = getattr(gate, "poll_once", None)
        if poll is not None:
            try:
                poll()
            except Exception:
                pass
        snap = getattr(gate, "snapshot", None)
        if snap is None:
            ok, reason = getattr(gate, "check", gate)()
            return bool(ok), str(reason)
        s = snap()
        if s.get("state") == "open":
            return True, ""
        return False, str(s.get("reason") or "liveOD's run state is unknown")

    def _on_trigger_toggled(self, checked):
        if checked and self._pulser is None and not self._pulser_loading:
            if make_trigger_pulser is None:
                self._pulser_error = f"ARTIQ trigger unavailable here: {_TRIGGER_ERROR}"
            else:
                self._pulser_loading = True
                self._pulser_error = ""
                self.trigger_status.setText("Setting up the ARTIQ trigger (kexp tables, "
                                            "device db)...")
                self.trigger_status.setVisible(True)
                run_check = self._trigger_run_check
                BackgroundCall(lambda: make_trigger_pulser(run_check), self._on_pulser_made, self)
        self._apply_trigger_to_source()
        self._render_trigger_status()
        self._update_controls()

    def _on_pulser_made(self, result, error):
        self._pulser_loading = False
        if error is not None:
            self._pulser_error = f"ARTIQ trigger unavailable: {type(error).__name__}: {error}"
            print(f"[trigger] {self._pulser_error}")
        else:
            self._pulser, self._pulser_error = result, ""
            print(f"[trigger] ready: {result.describe()}")
        if self._closing:
            return
        self._apply_trigger_to_source()
        self._render_trigger_status()
        self._update_controls()

    def _apply_trigger_to_source(self):
        """Give the source the pulser when the box is ticked and it can take
        triggered frames; take it away otherwise (the scan then snaps)."""
        set_trigger = getattr(self.source, "set_trigger", None)
        if set_trigger is None:
            return
        want = self._pulser if (self._trigger_wanted() and not self._trigger_refusal()) else None
        if getattr(self.source, "trigger", None) is want:
            return
        try:
            set_trigger(want)
        except Exception as e:          # during a triggered scan: it keeps its pulser
            print(f"[trigger] {e}")

    def _render_trigger_status(self):
        if self._pulser_loading:
            return
        if not self._trigger_wanted():
            text = ""
        else:
            why = self._trigger_refusal()
            if why:
                text = f"Triggered frames unavailable: {why}."
            else:
                text = (f"Scan frames are triggered from ARTIQ ({self._pulser.describe()}). A "
                        f"scan holds the ARTIQ core (the monitor yields; composite ops are "
                        f"fenced; the device state reads UNTRUSTED until it is handed back).")
        self.trigger_status.setText(text)
        self.trigger_status.setVisible(bool(text))

    def on_test_trigger(self):
        """Arm, one pulse, the frame it exposed, disarm -- the trigger path
        checked without a scan.  Takes the core like a scan: never while the
        run gate is closed."""
        if self._scanning or self._trigger_testing:
            return
        if not self._gate_open:
            self.trigger_status.setText(f"Not triggering: {self._gate_reason}")
            self.trigger_status.setVisible(True)
            return
        if not self._camera_connected() or self._camera_busy:
            self.trigger_status.setText("Connect the Andor first (andor button).")
            self.trigger_status.setVisible(True)
            return
        self._apply_trigger_to_source()
        why = self._trigger_refusal() or ("tick 'Trigger frames from ARTIQ' first"
                                          if not self._trigger_wanted() else "")
        if why:
            self.trigger_status.setText(f"Not triggering: {why}.")
            self.trigger_status.setVisible(True)
            return
        self._trigger_testing = True
        self._trigger_test_video = self.source.video_running()
        source = self.source
        self.trigger_status.setText("Taking one triggered frame (arming, one pulse)...")
        self.trigger_status.setVisible(True)
        self._update_controls()
        BackgroundCall(lambda: source.triggered_frame(), self._on_test_trigger_done, self)

    def _on_test_trigger_done(self, result, error):
        self._trigger_testing = False
        if self._closing:
            return
        report = getattr(self.source, "last_trigger_report", None) or {}
        if error is not None:
            text = f"Triggered frame FAILED: {type(error).__name__}: {error}"
            if report:
                text += f" -- {trigger_summary(report)}"
        else:
            frame, report = result
            if frame is not None:
                self.cam_img_item.setImage(frame.T, autoLevels=True)
            text = f"Triggered frame OK: {trigger_summary(report)}."
        notes = list(report.get("pulser_notes") or ())
        if notes:
            text += " " + notes[-1]
        print(f"[trigger] {text}")
        self.trigger_status.setText(text)
        self.trigger_status.setVisible(True)
        if self._trigger_test_video and self._camera_connected():
            self._trigger_test_video = False
            self.video_btn.setChecked(True)
            self._start_video()
        self._update_controls()

    # Scan
    def start_scan(self):
        if self._scanning:
            return
        if not self._gate_open:
            self.scan_progress.setText(f"Not scanning: {self._gate_reason}")
            return
        if not self._camera_connected() or self._camera_busy or self._trigger_testing:
            self.scan_progress.setText("Connect the Andor first (andor button).")
            return
        # frames on ARTIQ edges when asked for and possible; never a silent
        # fall-back to snaps when the box is ticked
        self._apply_trigger_to_source()
        if self._trigger_wanted():
            why = self._trigger_refusal()
            if why:
                self.scan_progress.setText(f"Not scanning: {why}.")
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
        self._scan_xs = xs
        self._scan_ys = ys
        nx, ny = len(xs), len(ys)

        # The scan owns the camera: it starts its own acquisition at every
        # position, so the free-running video has to stop for it.
        self._scan_was_running = self.source.video_running()
        if self._scan_was_running:
            self.source.stop_video()

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
            self.scan_preview_dlg.show()

        # Find out afresh whether the SLM server confirms each pattern -- it
        # may have been restarted with a different run_server.py since.
        self.slm.reset_reply_probe()
        self.scan_slm_mode.setText("")

        self._scanning = True
        self._scan_stopping = False
        self._scan_total = len(points)
        self._scan_done = 0
        self._scan_last_t = time.monotonic()
        self.scan_progress.setText(f"Scanning 0/{len(points)} ...")
        self._update_controls()

        # The gate is asked before every position; a run ends the scan.
        self.scan_worker = ScanWorker(
            self.slm, self.source, points,
            settle_s=self.settle_sb.value() / 1000.0,
            may_write=self.slm.gate,
        )
        self.scan_worker.shot_sig.connect(self._on_scan_shot)
        self.scan_worker.finished_sig.connect(self._on_scan_finished)
        self.scan_worker.start()

    def on_return_to_start(self):
        """Send the pattern back to where the last scan started -- on this click only.

        It used to happen by itself once the preview closed; a write deferred
        like that could land in the middle of a run.
        """
        if self._scanning or self._scan_start_center is None:
            return
        if not self._gate_open:
            self.scan_progress.setText(f"Not returned: {self._gate_reason}")
            return
        self.slm.set_center(*self._scan_start_center)

    @QtCore.pyqtSlot(int, int)
    def on_scan_spot_picked(self, cx, cy):
        """Left-click on a scan tile -> move the pattern to that tile's position.

        Ignored while a scan is running: the ScanWorker owns the center then and
        would overwrite the pick at the next grid point. Refused while the run
        gate is closed.
        """
        dlg = self.sender()
        if not isinstance(dlg, QtWidgets.QDialog):
            dlg = self.scan_preview_dlg
        if self._scanning:
            if dlg is not None:
                dlg.center_readout.setText(
                    "Scan still running -- click again once it finishes."
                )
            return
        if not self._gate_open:
            if dlg is not None:
                dlg.center_readout.setText(f"Not moved: {self._gate_reason}")
            return
        self.slm.set_center(int(cx), int(cy))

    def stop_scan(self):
        """
        Interrupt scan safely.
        Worker stops before the next position; the current one finishes.
        """
        if self._scanning and self.scan_worker is not None:
            self.scan_worker.stop()
            self._scan_stopping = True
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
        self._scan_stopping = False
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
        # The scan leaves the pattern parked where it last wrote it; it goes
        # back only on the Return now button.
        here = self.slm.get_center()
        if self._scan_start_center is not None and here != tuple(self._scan_start_center):
            parts.append(f"Pattern left at {here}; Return now puts it back at "
                         f"{tuple(self._scan_start_center)}.")
        report = getattr(self.source, "last_trigger_report", None)
        if report and getattr(self.source, "triggered", False):
            parts.append(f"ARTIQ-triggered frames: {trigger_summary(report)}.")
            notes = list(report.get("pulser_notes") or ())
            if notes:
                parts.append(notes[-1].rstrip(".") + ".")
        summary = " ".join(parts)
        print(f"[scan] {summary}")
        self.scan_progress.setText(summary)

        pending, self._handover_pending = self._handover_pending, None
        if pending is not None:
            # liveOD took the Andor over during the scan: follow it now, and
            # restart the video there if it ran before the scan
            self._on_handover(dict(pending, video=bool(pending.get("video")
                                                       or self._scan_was_running)))
        elif self._scan_was_running and self._camera_connected():
            self.video_btn.setChecked(True)
            self._start_video()
        self._update_controls()

        if not self._scan_live:
            grid = shots_to_grid(shots, nx, ny)
            dlg = FinalScanPreviewDialog(grid, self._scan_xs, self._scan_ys, parent=self,
                                         title=f"Scan Preview ({ny}x{nx})", note=summary)
            dlg.spot_picked.connect(self.on_scan_spot_picked)
            dlg.exec()
        elif self.scan_preview_dlg is not None and self.scan_preview_dlg.isVisible():
            self.scan_preview_dlg.set_note(summary)

    def closeEvent(self, event):
        self._closing = True
        self._gate_timer.stop()
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
            self.source.stop_video()
        except Exception:
            pass

        try:
            self.source.close()
        except Exception:
            pass

        own = self._own_source
        if own is not None:
            # the Andor served here: closed (if still open here), its server stopped
            try:
                own.shutdown()
            except Exception as e:
                print(f"[camera] stopping the spot finder's camera server failed: {e}")

        if self._pulser is not None:
            # a hold is already over (the scan was waited for); this closes the
            # monitor client, and releases the core if a hold is somehow left
            try:
                self._pulser.close()
            except Exception as e:
                print(f"[trigger] closing the ARTIQ trigger failed: {e}")

        self.slm.close()
        if self._owns_gate:
            # a poll can hang for seconds on an unreachable liveOD; not the close
            self.run_gate.stop(timeout=0.5)
        event.accept()


def make_trigger_pulser(run_check):
    """The ARTIQ pulser on the Andor's trigger line (artiq_trigger), with the
    window's run check.  Reads kexp's tables and the device db: called off
    the GUI thread.  Tests replace this."""
    if make_andor_trigger is None:
        raise RuntimeError(f"ARTIQ trigger unavailable here: {_TRIGGER_ERROR}")
    return make_andor_trigger(run_check=run_check)


def make_own_andor_source():
    """The Andor this window opens itself, served so that liveOD's camera host
    can take it over (served_source): the real Andor (EMCCDBackend) with the
    lab's readout settings, under liveOD's id for it, served on the lab
    network. Nothing is opened or served until its open(). Tests replace this."""
    return ServedAndorSource(camera_id=andor_camera_id, readout=andor_readout_params,
                             label="SLM spot finder")


def open_local_andor(exposure_s):
    """Open the Andor here, through the SDK, with the lab's readout settings.

    LocalAndorSource's open_camera. AndorEMCCD is looked up when this is
    called, not when the module is imported.
    """
    return AndorEMCCD(ExposureTime=exposure_s, gain=0.0, **andor_readout_params())


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


def andor_camera_id():
    """The Andor's camera id in liveOD's camera host, from kexp's cameras.andor
    by the host's own rule, so that liveOD finds its Andor on the spot finder's
    server when it needs it (ServedAndorSource's camera_id)."""
    try:
        from kexp.config.camera_id import camera_frame
        params = camera_frame().andor
    except Exception as e:
        print(f"[camera] kexp camera_id unavailable ({e}); serving the Andor as "
              f"{DEFAULT_ANDOR_CAMERA_ID}")
        return DEFAULT_ANDOR_CAMERA_ID
    return liveod_camera_id(params)


def parse_source_mode(argv=None):
    """'auto' (default), 'direct' (--direct) or 'stream' (--stream). Unknown
    arguments (Qt's own) are left alone."""
    parser = argparse.ArgumentParser(
        description="SLM spot finder. By default the Andor comes from liveOD's camera host "
                    "when liveOD serves it, else it is opened here.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--direct", action="store_true",
                       help="open the Andor here and never attach to liveOD's camera host "
                            "(release the camera in liveOD first); liveOD's camera host can "
                            "still take the Andor over when it needs it, and the spot finder "
                            "then stops using it")
    group.add_argument("--stream", action="store_true",
                       help="use liveOD's Andor through its camera host only; never open "
                            "the camera directly")
    args, _ = parser.parse_known_args(argv)
    return "direct" if args.direct else "stream" if args.stream else "auto"


class UnifiedExperiment():
    def build(self, source_mode="auto"):
        # The window finds its camera itself, off the GUI thread -- liveOD's
        # Andor, or the Andor opened here -- and can release and re-open it
        # later (andor button) without being closed.
        self.camera = None
        self.source_mode = source_mode

    def run(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        gui = UnifiedControlGUI(self.camera, source_mode=self.source_mode)
        gui.show()
        app.exec()

if __name__ == "__main__":
    ue = UnifiedExperiment()
    ue.build(source_mode=parse_source_mode(sys.argv[1:]))
    ue.run()
