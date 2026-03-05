import socket
import json
import numpy as np
from PyQt6 import QtCore
import pyqtgraph as pg
from PIL import Image, ImageDraw


class SLMController(QtCore.QObject):
    """
    Holds SLM state + networking + generates preview image.
    """
    state_changed = QtCore.pyqtSignal()  # emitted when state changes

    def __init__(self, canvas_res=(1920, 1200), server_ip="192.168.1.102", server_port=5000):
        super().__init__()
        self.canvas_res = canvas_res

        # state
        self.spot_center = [994, 824]
        self.spot_radius = 10

        self.grating_center = [994, 824]
        self.grating_size = 300
        self.grating_spacing = 6
        self.angle_deg = 0.0

        self.mode = "spot"

        # network
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((self.server_ip, self.server_port))
            print("Connected to SLM server.")
        except Exception as e:
            print(f"SLM Connection Failed: {e}")
            self.sock = None

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        except:
            pass

    def get_center(self):
        c = self.spot_center if self.mode == "spot" else self.grating_center
        return int(c[0]), int(c[1])

    def set_mode(self, mode: str):
        self.mode = "spot" if mode == "spot" else "grating"
        self.state_changed.emit()
        self.send_update()

    def set_center(self, cx: int, cy: int):
        cx = max(0, min(self.canvas_res[0] - 1, int(cx)))
        cy = max(0, min(self.canvas_res[1] - 1, int(cy)))
        if self.mode == "spot":
            self.spot_center = [cx, cy]
        else:
            self.grating_center = [cx, cy]
        self.state_changed.emit()
        self.send_update()

    def nudge_center(self, dx: int, dy: int):
        cx, cy = self.get_center()
        self.set_center(cx + dx, cy + dy)

    def send_update(self):
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

    def render_preview_image(self) -> np.ndarray:
        """
        Returns a 2D uint8 image (L mode) for preview.
        Keep same convention you used before: caller can .T if needed.
        """
        img = Image.new("L", self.canvas_res, 255)
        draw = ImageDraw.Draw(img)

        if self.mode == "spot":
            x, y = self.spot_center
            r = self.spot_radius
            draw.ellipse((x - r, y - r, x + r, y + r), fill=0)
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
