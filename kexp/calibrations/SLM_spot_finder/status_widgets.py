import threading

from PyQt6 import QtCore, QtWidgets

# liveOD's camera-button palette, so a device reads the same colour here as there:
# closed grey, loading purple, open green, grabbing blue, failed red.
from waxx.util.live_od.gui.camera_menu import STATES


class StatusPill(QtWidgets.QPushButton):
    """liveOD's camera connect/disconnect button, for one device.

    Coloured by state; clicking it is up to the owner (connect, disconnect,
    re-check). The tooltip carries the detail -- the last error, what the
    click will do.
    """

    def __init__(self, name, parent=None):
        super().__init__(name, parent)
        self.name = name
        self.state = None
        self.set_state("closed")

    def set_state(self, state, detail="", action=""):
        self.state = state if state in STATES else "closed"
        color, word = STATES[self.state]
        # the same style as waxx.util.live_od.gui.camera_menu
        self.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; font-weight: bold; "
            f"border: none; border-radius: 8px; padding: 1px 8px; }} "
            f"QPushButton:disabled {{ color: rgba(255, 255, 255, 140); }}")
        tip = f"{self.name}: {word}."
        if action:
            tip += f" Click to {action}."
        if detail:
            tip += f"\n{detail}"
        self.setToolTip(tip)


class BackgroundCall(QtCore.QObject):
    """Run ``fn()`` on a plain thread; hand ``(result, error)`` to ``on_done`` on the GUI thread.

    For the blocking device calls -- opening the Andor, finding the PDXC server,
    a stage throw -- that would otherwise freeze the window for seconds.
    """
    _done = QtCore.pyqtSignal(object, object)

    def __init__(self, fn, on_done, parent):
        super().__init__(parent)   # the parent keeps this alive until delivered
        self._fn = fn
        self._on_done = on_done
        self._done.connect(self._deliver)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result, error = self._fn(), None
        except Exception as e:
            result, error = None, e
        self._done.emit(result, error)

    @QtCore.pyqtSlot(object, object)
    def _deliver(self, result, error):
        try:
            self._on_done(result, error)
        finally:
            self.deleteLater()
