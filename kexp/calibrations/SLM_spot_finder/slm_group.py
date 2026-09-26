import socket
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PyQt6 import QtCore
import pyqtgraph as pg
from PIL import Image, ImageDraw
from kexp.config import ExptParams

CONNECT_TIMEOUT_S = 1.0
# A server that has said nothing this long after a command that asked for a
# reply is taken to be the old run_server.py, which never replies.
RECEIPT_TIMEOUT_S = 1.0
# How long a server that does reply may take to put a pattern up. Generous: an
# hourly REINIT (a few seconds) can be in its queue ahead of the command.
APPLY_TIMEOUT_S = 10.0


@dataclass
class SLMSendResult:
    """What is known about one command once it has been sent.

    ``applied`` is True when the server said the pattern is on the SLM, and
    None when the server does not say (the old run_server.py): the command
    was delivered, but when the pattern went up is not known.
    """
    ok: bool
    applied: Optional[bool] = None
    center: Optional[tuple] = None          # the center that was requested
    t_sent: Optional[float] = None          # time.monotonic() after sendall
    t_applied: Optional[float] = None       # time.monotonic() at the "applied" reply
    server_apply_s: Optional[float] = None  # the server's own generate + upload time
    error: str = ""


class _Outgoing:
    """One item for the sender thread: a command, or (command None) a probe."""

    def __init__(self, command=None, want_reply=False):
        self.command = command
        self.want_reply = want_reply
        self.done = threading.Event()
        self.result = None


class SLMController(QtCore.QObject):
    """
    Holds SLM state + networking + generates preview image.

    Every command goes out on its own short connection from one sender thread,
    the way waxx.control.slm.SLM sends from an experiment. The SLM server
    serves one connection at a time, so the connection this used to hold open
    for the life of the GUI kept every experiment's SLM command waiting until
    the GUI was closed.
    """
    state_changed = QtCore.pyqtSignal()  # emitted when state changes
    link_changed = QtCore.pyqtSignal(str, str)  # pill state, detail

    def __init__(self, canvas_res=(1920, 1200), server_ip="192.168.1.102", server_port=5000):
        super().__init__()
        self.canvas_res = canvas_res
        self._lock = threading.RLock()

        # state
        p = ExptParams()
        self.spot_center = [p.px_slm_phase_mask_position_x, p.px_slm_phase_mask_position_y]
        self.spot_radius = 10

        self.grating_center = [p.px_slm_grating_position_x, p.px_slm_grating_position_y]
        self.grating_size = 300
        self.grating_spacing = 6
        self.angle_deg = 0.0

        self.mode = "spot"

        # network
        self.server_ip = server_ip
        self.server_port = server_port
        # None until a command has asked for replies; then whether the server
        # gave any. reset_reply_probe() asks again.
        self.server_replies = None
        self._seq = 0
        self._last_link = None
        self._cv = threading.Condition()
        self._pending = deque()
        self._closing = False
        self._sender = threading.Thread(target=self._send_loop, name="slm-sender", daemon=True)
        self._sender.start()

    def close(self):
        with self._cv:
            self._closing = True
            self._cv.notify_all()
        self._sender.join(timeout=2.0)

    def get_center(self):
        with self._lock:
            c = self.spot_center if self.mode == "spot" else self.grating_center
            return int(c[0]), int(c[1])

    def set_mode(self, mode: str):
        self.mode = "spot" if mode == "spot" else "grating"
        self.state_changed.emit()
        self.send_update()

    def _set_center_state(self, cx: int, cy: int):
        cx = max(0, min(self.canvas_res[0] - 1, int(cx)))
        cy = max(0, min(self.canvas_res[1] - 1, int(cy)))
        with self._lock:
            if self.mode == "spot":
                self.spot_center = [cx, cy]
            else:
                self.grating_center = [cx, cy]

    def set_center(self, cx: int, cy: int):
        self._set_center_state(cx, cy)
        self.state_changed.emit()
        self.send_update()

    def set_center_and_wait(self, cx: int, cy: int) -> SLMSendResult:
        """Move the pattern and block until the server has it up, if it says so.

        For the scan thread. Returns once the server replied "applied", or --
        for a server that does not reply -- once the command was delivered.
        Bounded by the timeouts at the top of this module.
        """
        self._set_center_state(cx, cy)
        self.state_changed.emit()
        item = self._enqueue(_Outgoing(self._command(), want_reply=True))
        item.done.wait()
        return item.result

    def check_link(self):
        """Ask whether the server accepts a connection, without sending a pattern."""
        self._enqueue(_Outgoing())

    def reset_reply_probe(self):
        """Forget whether the server replies; the next scan command finds out."""
        self.server_replies = None

    def nudge_center(self, dx: int, dy: int):
        cx, cy = self.get_center()
        self.set_center(cx + dx, cy + dy)

    def reset_center_to_default(self):
        """Reset the center of the current mode (spot/grating) back to its default value."""
        p = ExptParams()
        if self.mode == "spot":
            self.set_center(p.px_slm_phase_mask_position_x, p.px_slm_phase_mask_position_y)
        else:
            self.set_center(p.px_slm_grating_position_x, p.px_slm_grating_position_y)

    def _command(self) -> dict:
        with self._lock:
            center = self.spot_center if self.mode == "spot" else self.grating_center
            dim = self.spot_radius if self.mode == "spot" else self.grating_size
            return {
                "mask": self.mode,
                "center": [int(center[0]), int(center[1])],
                "dimension": dim,
                "spacing": self.grating_spacing,
                "angle": self.angle_deg,
                "phase": 3,
                "initialize": False,
            }

    def send_update(self):
        self._enqueue(_Outgoing(self._command()))

    # ------------------------------------------------------------------
    # Sender thread
    # ------------------------------------------------------------------

    def _enqueue(self, item: _Outgoing) -> _Outgoing:
        with self._cv:
            if item.command is not None and not item.want_reply:
                # Each command carries the whole SLM state, so a newer update
                # supersedes any update still waiting to go. Keeps a dragged
                # slider from queueing hundreds of sends behind a dead server.
                self._pending = deque(p for p in self._pending
                                      if p.command is None or p.want_reply)
            self._pending.append(item)
            self._cv.notify()
        return item

    def _send_loop(self):
        while True:
            with self._cv:
                while not self._pending and not self._closing:
                    self._cv.wait()
                if not self._pending:
                    return
                item = self._pending.popleft()
            try:
                item.result = self._transmit(item)
            except Exception as e:
                item.result = SLMSendResult(ok=False, error=f"{type(e).__name__}: {e}")
            item.done.set()
            self._report(item)

    def _transmit(self, item: _Outgoing) -> SLMSendResult:
        center = tuple(item.command["center"]) if item.command else None
        try:
            with socket.create_connection((self.server_ip, self.server_port),
                                          timeout=CONNECT_TIMEOUT_S) as sock:
                if item.command is None:
                    return SLMSendResult(ok=True)
                command = dict(item.command)
                seq = None
                if item.want_reply:
                    self._seq += 1
                    seq = command["seq"] = self._seq
                sock.sendall(json.dumps(command).encode() + b"\n")
                result = SLMSendResult(ok=True, center=center, t_sent=time.monotonic())
                if seq is None or self.server_replies is False:
                    return result
                return self._await_applied(sock, seq, result)
        except OSError as e:
            return SLMSendResult(ok=False, center=center, error=f"{type(e).__name__}: {e}")

    def _await_applied(self, sock, seq, result: SLMSendResult) -> SLMSendResult:
        got_receipt = False
        buf = b""
        while True:
            limit = APPLY_TIMEOUT_S if (got_receipt or self.server_replies) else RECEIPT_TIMEOUT_S
            remaining = result.t_sent + limit - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict) or msg.get("seq") != seq:
                    continue
                status = msg.get("status")
                if status == "queued":
                    got_receipt = True
                    self.server_replies = True
                elif status == "applied":
                    self.server_replies = True
                    applied = tuple(int(v) for v in (msg.get("center") or ()))
                    if applied != result.center:
                        result.ok = False
                        result.error = (f"server applied center {applied}, "
                                        f"not the requested {result.center}")
                        return result
                    result.applied = True
                    result.t_applied = time.monotonic()
                    result.server_apply_s = msg.get("t_apply_s")
                    return result
                else:
                    result.ok = False
                    result.error = f"server replied {status!r}: {msg.get('error', '')}".rstrip(": ")
                    return result

        if not got_receipt and self.server_replies is None:
            # Nothing came back at all: the old run_server.py, which never
            # replies. The command was delivered; when it went up is unknown.
            self.server_replies = False
            return result
        result.ok = False
        result.error = ("server received the command but did not report it applied "
                        f"within {APPLY_TIMEOUT_S:.0f} s" if got_receipt else
                        f"no reply from the server within {APPLY_TIMEOUT_S:.0f} s")
        return result

    def _report(self, item: _Outgoing):
        r = item.result
        where = f"SLM server {self.server_ip}:{self.server_port}"
        if not r.ok:
            state, detail = "failed", f"{where}: {r.error}"
        elif item.command is None:
            state, detail = "open", f"{where} accepts connections"
        else:
            confirms = {True: "it confirms each pattern",
                        False: "it does not confirm patterns (old run_server.py)",
                        None: "not yet known whether it confirms patterns"}[self.server_replies]
            state, detail = "open", f"{where}: last command delivered; {confirms}"
        if (state, detail) != self._last_link:
            self._last_link = (state, detail)
            print(f"[slm] {detail}")
            self.link_changed.emit(state, detail)

    def render_preview_image(self) -> np.ndarray:
        """
        Returns a 2D uint8 image (L mode) for preview.
        Keep same convention you used before: caller can .T if needed.
        """
        img = Image.new("L", self.canvas_res, 255)
        draw = ImageDraw.Draw(img)

        with self._lock:
            spot_center = list(self.spot_center)
            grating_center = list(self.grating_center)

        if self.mode == "spot":
            x, y = spot_center
            r = self.spot_radius
            draw.ellipse((x - r, y - r, x + r, y + r), fill=0)
        else:
            cx, cy = grating_center
            half = self.grating_size // 2
            period = self.grating_spacing
            theta = np.deg2rad(self.angle_deg)
            c, s = np.cos(theta), np.sin(theta)

            for y in range(max(0, cy - half), min(self.canvas_res[1], cy + half)):
                for x in range(max(0, cx - half), min(self.canvas_res[0], cx + half)):
                    proj = (x - cx) * c + (y - cy) * s
                    if (proj % period) < (period * 0.5):
                        draw.point((x, y), fill=0)

        return np.array(img, dtype=np.uint8)

    def set_spot_radius(self, r: int):
        self.spot_radius = max(1, int(r))
        self.state_changed.emit()
        self.send_update()


    def set_grating_size(self, size: int):
        size = int(size)
        self.grating_size = max(2, size)
        self.state_changed.emit()
        self.send_update()

    def set_grating_spacing(self, spacing: int):
        spacing = int(spacing)
        self.grating_spacing = max(2, int(spacing))
        self.state_changed.emit()
        self.send_update()

    def set_angle_deg(self, angle: float):
        self.angle_deg = float(angle)
        self.state_changed.emit()
        self.send_update()



class SLMPreviewWidget(pg.GraphicsLayoutWidget):
    """
    A small widget that shows the SLM preview:
    - fixed orientation (invertY True)
    - no axes
    - canvas not draggable
    - only ImageItem draggable
    """
    dragged_to = QtCore.pyqtSignal(int, int)  # (cx, cy)

    def __init__(self, controller: SLMController, height=300, parent=None):
        super().__init__(parent=parent)
        self.controller = controller
        self.setFixedHeight(height)

        self.plot = self.addPlot()
        for ax in ("bottom", "left", "top", "right"):
            self.plot.hideAxis(ax)

        self.plot.setMenuEnabled(False)
        vb = self.plot.getViewBox()
        vb.setMouseEnabled(x=False, y=False)
        vb.setMenuEnabled(False)
        vb.setDefaultPadding(0.0)

        self.plot.invertY(True)
        self.plot.setAspectLocked(True)

        self.img_item = pg.ImageItem()
        self.plot.addItem(self.img_item)

        self._dragging = False
        self.img_item.mousePressEvent = self._start_drag
        self.img_item.mouseMoveEvent = self._do_drag
        self.img_item.mouseReleaseEvent = self._stop_drag

        self.refresh()

    def refresh(self):
        arr = self.controller.render_preview_image()
        # Keep your existing convention with .T
        self.img_item.setImage(arr.T)

    def _start_drag(self, event):
        self._dragging = True

    def _stop_drag(self, event):
        self._dragging = False

    def _do_drag(self, event):
        if not self._dragging:
            return
        pos = event.pos()
        cx = int(pos.x())
        cy = int(pos.y())
        cx = max(0, min(self.controller.canvas_res[0] - 1, cx))
        cy = max(0, min(self.controller.canvas_res[1] - 1, cy))
        self.dragged_to.emit(cx, cy)
