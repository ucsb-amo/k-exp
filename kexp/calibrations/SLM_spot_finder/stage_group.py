"""The APD pickoff stage, driven from the spot finder.

The stage carries a beamsplitter: IN sends the light to the APD and blocks the
Andor, OUT leaves the Andor clear. Nothing here moves it on its own -- not at
startup, not before a scan. It moves when one of the two buttons is pressed.

Uses kexp's APDStageClient, the one sanctioned path to the PDXC. The position
shown is the one the PDXC server last commanded, not a sensor reading: a stage
moved by hand reads whatever it was last sent, and one left after a jog or an
interrupted throw reads "unknown".
"""

from PyQt6 import QtCore, QtWidgets

from kexp.control.misc.pdxc_apd_stage import (
    APDStageClient, POSITION_IN, POSITION_OUT, POSITION_UNKNOWN)

from status_widgets import StatusPill, BackgroundCall

DISCOVERY_TIMEOUT_S = 3.0

POSITION_TEXT = {
    POSITION_OUT: "OUT: Andor clear",
    POSITION_IN: "IN: light to APD, Andor blocked",
    POSITION_UNKNOWN: "unknown (last move was a jog, or was interrupted)",
}


class StageGroup(QtWidgets.QGroupBox):
    """Position readout, Out / In buttons, and a status pill for the PDXC server."""

    def __init__(self, parent=None):
        super().__init__("APD Stage", parent)
        self.stage = None      # APDStageClient while connected
        self.position = None   # POSITION_* while connected, else None
        self._busy = False
        self._locked = False

        self.pill = StatusPill("stage")
        self.pill.clicked.connect(self._on_pill_clicked)

        g = QtWidgets.QGridLayout()
        g.addWidget(QtWidgets.QLabel("Position:"), 0, 0)
        self.position_label = QtWidgets.QLabel("not connected")
        self.position_label.setToolTip(
            "The position the PDXC server last commanded -- not a sensor reading.")
        g.addWidget(self.position_label, 0, 1)

        self.out_btn = QtWidgets.QPushButton("Move Out (Andor)")
        self.out_btn.clicked.connect(lambda: self.move(POSITION_OUT))
        g.addWidget(self.out_btn, 1, 0)

        self.in_btn = QtWidgets.QPushButton("Move In (APD)")
        self.in_btn.clicked.connect(lambda: self.move(POSITION_IN))
        g.addWidget(self.in_btn, 1, 1)

        self.force_cb = QtWidgets.QCheckBox("force")
        self.force_cb.setToolTip(
            "Drive the full throw even when the server says the stage is already "
            "there -- e.g. after it was moved by hand.")
        g.addWidget(self.force_cb, 2, 0)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        g.addWidget(self.refresh_btn, 2, 1)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: gray;")
        self.status.setWordWrap(True)
        g.addWidget(self.status, 3, 0, 1, 2)

        self.setLayout(g)
        self._render()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect_stage(self):
        if self._busy or self.stage is not None:
            return
        self._busy = True
        self.pill.set_state("loading", "Looking for the PDXC server...")
        self.status.setText("Looking for the PDXC server...")
        self._update_enabled()
        BackgroundCall(self._find_server, self._on_connected, self)

    @staticmethod
    def _find_server():
        stage = APDStageClient(discovery_timeout=DISCOVERY_TIMEOUT_S, raise_on_error=True)
        return stage, (stage.position() if stage.connected else None)

    def _on_connected(self, result, error):
        self._busy = False
        if error is not None:
            self._fail(f"PDXC server did not answer: {error}")
            return
        stage, position = result
        if not stage.connected:
            self._fail("PDXC server not found. It runs under the Server Dashboard.")
            return
        self.stage = stage
        self.position = position
        self.status.setText("")
        self._render()

    def disconnect_stage(self):
        """Forget the server. The stage does not move."""
        if self._busy:
            return
        self.stage = None
        self.position = None
        self.status.setText("")
        self._render()

    def _on_pill_clicked(self):
        if self.stage is None:
            self.connect_stage()
        else:
            self.disconnect_stage()

    # ------------------------------------------------------------------
    # Moves
    # ------------------------------------------------------------------

    def move(self, state):
        if self.stage is None or self._busy or self._locked:
            return
        force = self.force_cb.isChecked()
        stage = self.stage
        self._busy = True
        self.pill.set_state("loading", f"Moving {state}...")
        self.status.setText(f"Moving {state}{' (forced)' if force else ''}...")
        self._update_enabled()

        def work():
            reply = stage.move_to(state, force=force)
            return reply, stage.position()

        BackgroundCall(work, self._on_moved, self)

    def _on_moved(self, result, error):
        self._busy = False
        if error is not None:
            self._fail(f"Move failed: {error}")
            return
        reply, self.position = result
        self.status.setText(f"Stage: {reply}.")
        self._render()

    def refresh(self):
        if self.stage is None or self._busy:
            return
        self._busy = True
        self._update_enabled()
        BackgroundCall(self.stage.position, self._on_refreshed, self)

    def _on_refreshed(self, position, error):
        self._busy = False
        if error is not None:
            self._fail(f"Position query failed: {error}")
            return
        self.position = position
        self._render()

    def set_locked(self, locked: bool):
        """No moves while a scan runs: the frames would stop meaning anything."""
        self._locked = bool(locked)
        self._update_enabled()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _fail(self, msg):
        # Drop the client so the next click on the pill looks for the server again.
        self.stage = None
        self.position = None
        print(f"[stage] {msg}")
        self._render()
        self.pill.set_state("failed", msg, action="connect again")
        self.status.setText(msg)

    def _render(self):
        if self.stage is None:
            self.pill.set_state("closed", "", action="connect")
            self.position_label.setText("not connected")
            self.position_label.setStyleSheet("")
        else:
            self.pill.set_state("open", "PDXC server found. The stage does not move on "
                                "disconnect.", action="disconnect")
            self.position_label.setText(POSITION_TEXT.get(self.position, str(self.position)))
            self.position_label.setStyleSheet(
                "color: #c62828; font-weight: bold;" if self.position == POSITION_IN else "")
        self._update_enabled()

    def _update_enabled(self):
        can_move = self.stage is not None and not self._busy and not self._locked
        for w in (self.out_btn, self.in_btn, self.force_cb, self.refresh_btn):
            w.setEnabled(can_move)
        self.pill.setEnabled(not self._busy and not self._locked)
