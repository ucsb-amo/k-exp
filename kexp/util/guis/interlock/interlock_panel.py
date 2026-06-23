"""interlock_panel.py — Qt panels for the interlock.

Two flavors:

* :class:`InterlockPanel` — full control: status display, plot, Enable
  Magnets (confirm dialog), Reset Interlock, Manual Kill.  Used on the
  *server* dashboard.
* :class:`InterlockClientPanel` — read-only status + plot.  No controls
  that can affect hardware.  Used on the *client* dashboard.

Both panels share the same body builder; the client variant just hides
the action buttons.

Per IT13, both panels react to ``applicationStateChanged`` (sleep/wake) by
forcing the conn badge to "unknown" until the next snapshot arrives.

Construction never blocks: the body appears immediately with placeholder
text; the :class:`InterlockClient` is constructed in a background thread
and the :class:`SnapshotPoller` starts once it succeeds.  If discovery
fails, the panel shows a red banner with retry.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from waxx.util.dashboard.embed_helpers import WidgetPanelBase, auto_cleanup_timers
from waxx.util.dashboard.widgets import CollapsibleGroupBox
from kexp.util.guis.interlock import interlock_safe_mode as _sm


_LOG = logging.getLogger("kexp.dashboard.panel.interlock")

_STATE_COLOR = {
    _sm.STATE_OK: ("#2e8b57", "white", "Interlock OK"),
    _sm.STATE_WARMUP: ("#d4a017", "white", "Warmup"),
    _sm.STATE_TRIPPED: ("#b22222", "white", "INTERLOCK TRIPPED"),
    _sm.STATE_SAFE_MODE: ("#8b0000", "white", "SAFE MODE"),
    _sm.STATE_UNKNOWN: ("#888", "white", "Unknown"),
}


class _ClientBuildWorker(QThread):
    """Construct InterlockClient on a background thread (discovery can take seconds)."""
    done = pyqtSignal(object, object)  # (client_or_None, exception_or_None)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self) -> None:
        try:
            from kexp.util.guis.interlock.interlock_client import InterlockClient  # noqa: PLC0415
            client = InterlockClient(discovery_timeout=3.0, timeout=1.5)
            self.done.emit(client, None)
        except BaseException as exc:  # noqa: BLE001
            self.done.emit(None, exc)


class _InterlockBodyBase(WidgetPanelBase):
    """Shared body widget for both server- and client-side panels."""

    def __init__(self, read_only: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._read_only = bool(read_only)
        self._client = None
        self._poller = None
        self._plot = None
        self._curves: dict = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(4)

        # Two-column body: status + kill stacked vertically on the left,
        # plot fills the right.  Gives the plot the full panel height
        # instead of cramping it under a wide top bar.
        body_row = QHBoxLayout()
        body_row.setSpacing(8)
        outer.addLayout(body_row, 1)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)

        self._status_btn = QPushButton("Connecting…", self)
        self._status_btn.setEnabled(False)
        self._status_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_status_style(_sm.STATE_UNKNOWN, "connecting…")
        left_col.addWidget(self._status_btn)

        # Server-only Magnets toggle (sits directly under Interlock OK).
        if not self._read_only:
            self._magnets_btn = QPushButton("Magnets …", self)
            self._magnets_btn.setEnabled(False)
            self._magnets_btn.setMinimumWidth(0)
            self._magnets_btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self._magnets_btn.clicked.connect(self._on_magnets_clicked)
            self._magnets_state: Optional[bool] = None  # tri-state: None/True/False
            self._apply_magnets_style(None)
            left_col.addWidget(self._magnets_btn)
        else:
            self._magnets_btn = None
            self._magnets_state = None

        # Metric labels stacked under the buttons.
        self._temp_lbl = QLabel("Temp: --", self)
        self._flow_lbl = QLabel("Flow: --", self)
        self._age_lbl = QLabel("Age: --", self)
        for w in (self._temp_lbl, self._flow_lbl, self._age_lbl):
            w.setStyleSheet("QLabel { font-family: Consolas, monospace; font-size: 11px; }")
            w.setMinimumWidth(0)
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            left_col.addWidget(w)
        left_col.addStretch(1)

        left_wrap = QWidget(self)
        left_wrap.setLayout(left_col)
        left_wrap.setMaximumWidth(180)
        body_row.addWidget(left_wrap, 0)

        # Reset Interlock removed (no-op on the controller).
        self._reset_btn = None
        self._enable_btn = None
        self._kill_btn = None

        # Plot (lazy import to avoid blocking the panel).
        self._plot_group = CollapsibleGroupBox("Temperature / Flow", expanded=True)
        body_row.addWidget(self._plot_group, 1)
        self._init_plot()

        # IT13: react to sleep/wake.
        try:
            QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)
        except Exception:
            pass

        # Begin async client construction; do NOT block here.
        self._build_worker = _ClientBuildWorker()
        self._build_worker.done.connect(self._on_client_built)
        QTimer.singleShot(0, self._build_worker.start)

    # ------------------------------------------------------------------
    # Plot setup
    # ------------------------------------------------------------------

    def _init_plot(self) -> None:
        try:
            import pyqtgraph as pg  # noqa: PLC0415
        except Exception:
            self._plot_group.addWidget(QLabel("pyqtgraph not available"))
            return
        plot = pg.PlotWidget()
        plot.setBackground("w")
        plot.showGrid(x=True, y=True)
        plot.setLabel("left", "Temp (°C)", color="#c00")
        # Tight axis & no bottom label - the x axis is obvious ("recent
        # time, seconds") and was eating ~30 px of vertical space.
        plot.setLabel("bottom", "")
        ax_b = plot.getAxis("bottom")
        ax_l = plot.getAxis("left")
        try:
            ax_b.setHeight(18)
            ax_l.setWidth(36)
        except Exception:
            pass
        try:
            plot.getPlotItem().setContentsMargins(0, 4, 4, 0)
        except Exception:
            pass
        plot.setYRange(15, 35)
        plot.addLegend(offset=(10, 5))

        # Second ViewBox on the right axis for flow voltages (different scale).
        self._flow_vb = pg.ViewBox()
        plot.scene().addItem(self._flow_vb)
        plot.getAxis("right").linkToView(self._flow_vb)
        plot.showAxis("right")
        plot.setLabel("right", "Flow (V)", color="#080")
        try:
            plot.getAxis("right").setWidth(36)
        except Exception:
            pass
        self._flow_vb.setXLink(plot)
        self._flow_vb.setYRange(2, 8)

        def _sync_vb():
            self._flow_vb.setGeometry(plot.getViewBox().sceneBoundingRect())
            self._flow_vb.linkedViewChanged(plot.getViewBox(), self._flow_vb.XAxis)
        _sync_vb()
        plot.getViewBox().sigResized.connect(_sync_vb)

        self._plot = plot
        self._curves["temp"] = plot.plot(
            [], [], pen=pg.mkPen("#c00", width=1.2), name="Temp"
        )
        flow_colors = ("#080", "#06c", "#08a", "#a0a")
        for i, color in enumerate(flow_colors, start=1):
            curve = pg.PlotCurveItem(pen=pg.mkPen(color, width=1.8), name=f"Flow {i}")
            self._flow_vb.addItem(curve)
            self._curves[f"flow{i}"] = curve
        self._plot_group.addWidget(plot)
        self._t0 = time.monotonic()
        self._history: dict = {k: [] for k in ("t", "temp", "flow1", "flow2", "flow3", "flow4")}
        self._history_max = 600  # ~10 min at 1 Hz

    # ------------------------------------------------------------------
    # Client/poller wiring
    # ------------------------------------------------------------------

    def _on_client_built(self, client, exc) -> None:
        if exc is not None:
            self._apply_status_style(_sm.STATE_UNKNOWN, f"server unreachable: {type(exc).__name__}")
            _LOG.warning("InterlockClient construction failed: %r", exc)
            # Retry every 5 s.
            QTimer.singleShot(5000, self._restart_build)
            return
        self._client = client
        from waxx.util.dashboard.snapshot_poller import SnapshotPoller  # noqa: PLC0415
        self._poller = SnapshotPoller(client, panel_id="interlock", parent=self)
        self._poller.snapshot_received.connect(self._apply_snapshot)
        self._poller.conn_changed.connect(self._on_conn_changed)
        self._poller.start()

    def _restart_build(self) -> None:
        self._build_worker = _ClientBuildWorker()
        self._build_worker.done.connect(self._on_client_built)
        self._build_worker.start()

    # ------------------------------------------------------------------
    # Snapshot handling
    # ------------------------------------------------------------------

    def _apply_snapshot(self, snap: dict) -> None:
        state = str(snap.get("state", _sm.STATE_UNKNOWN))
        msg = str(snap.get("message", ""))
        self._apply_status_style(state, msg)

        # Metric labels.  JSON converts integer dict keys to strings on the
        # wire, so the snapshot's flow_v has '1'/'2'/'3'/'4' as keys.  Coerce
        # to int-keyed dict for downstream code.
        temp = snap.get("temperature_c")
        raw_flow = snap.get("flow_v") or {}
        flow: dict = {}
        for k, v in raw_flow.items():
            try:
                flow[int(k)] = float(v)
            except (TypeError, ValueError):
                pass
        age = snap.get("last_data_age_s")
        self._temp_lbl.setText(f"Temp: {temp:.2f} °C" if isinstance(temp, (int, float)) else "Temp: --")
        if flow:
            flow_txt = "  ".join(f"F{k}={v:.2f}V" for k, v in sorted(flow.items()))
            self._flow_lbl.setText(f"Flow: {flow_txt}")
        else:
            self._flow_lbl.setText("Flow: --")
        if isinstance(age, (int, float)):
            self._age_lbl.setText(f"Age: {age:.1f}s")
        else:
            self._age_lbl.setText("Age: --")

        # Action button gating.
        if not self._read_only and self._magnets_btn is not None:
            magnets_enabled = snap.get("magnets_enabled")
            in_safe = state == _sm.STATE_SAFE_MODE
            if magnets_enabled is True:
                self._magnets_state = True
                self._magnets_btn.setEnabled(not in_safe)
            elif magnets_enabled is False:
                self._magnets_state = False
                # Only allow Enable when interlock state is OK.
                self._magnets_btn.setEnabled(not in_safe and state == _sm.STATE_OK)
            else:
                self._magnets_state = None
                self._magnets_btn.setEnabled(False)
            self._apply_magnets_style(self._magnets_state)

        # Plot append.
        if self._plot is not None and isinstance(temp, (int, float)):
            t = time.monotonic() - self._t0
            h = self._history
            h["t"].append(t)
            h["temp"].append(temp)
            for i in (1, 2, 3, 4):
                v = flow.get(i)
                h[f"flow{i}"].append(float(v) if isinstance(v, (int, float)) else float("nan"))
            # Trim.
            if len(h["t"]) > self._history_max:
                for k in h:
                    h[k] = h[k][-self._history_max:]
            self._curves["temp"].setData(h["t"], h["temp"])
            for i in (1, 2, 3, 4):
                curve = self._curves[f"flow{i}"]
                ys = h[f"flow{i}"]
                # Filter out NaN runs so pyqtgraph doesn't draw across gaps.
                import numpy as _np  # noqa: PLC0415
                arr_y = _np.asarray(ys, dtype=float)
                arr_x = _np.asarray(h["t"], dtype=float)
                mask = ~_np.isnan(arr_y)
                if mask.any():
                    curve.setData(arr_x[mask], arr_y[mask])
                else:
                    curve.setData([], [])

    def _on_conn_changed(self, status: str, detail: str) -> None:
        if status != "connected":
            # Don't override the service state if we just lost the polling link.
            self._apply_status_style(_sm.STATE_UNKNOWN, f"conn: {detail}" if detail else "conn lost")

    def _apply_status_style(self, state: str, msg: str) -> None:
        bg, fg, label = _STATE_COLOR.get(state, _STATE_COLOR[_sm.STATE_UNKNOWN])
        # When everything's OK, show just the label — no noisy suffix.
        if state == _sm.STATE_OK or not msg:
            text = label
        else:
            text = f"{label} — {msg}"
        self._status_btn.setText(text)
        self._status_btn.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; color: {fg};"
            " font-size: 16px; font-weight: 700; padding: 8px; border-radius: 4px; }"
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _apply_magnets_style(self, state: Optional[bool]) -> None:
        """Render the single Magnets button per current state.

        state is True (currently enabled — button says "Kill Magnets" red),
        False (currently off — button says "Enable Magnets…" green),
        or None (unknown — button says "Magnets …" gray).
        """
        if self._magnets_btn is None:
            return
        if state is True:
            self._magnets_btn.setText("Kill Magnets")
            self._magnets_btn.setStyleSheet(
                "QPushButton { background-color: #c46666; color: white;"
                " font-weight: 600; padding: 4px 10px; border-radius: 3px; }"
                "QPushButton:hover { background-color: #b85a5a; }"
                "QPushButton:disabled { background-color: #5a3a3a; color: #aaa; }"
            )
        elif state is False:
            self._magnets_btn.setText("Enable Magnets…")
            self._magnets_btn.setStyleSheet(
                "QPushButton { background-color: #2e8b57; color: white;"
                " font-weight: 600; padding: 4px 10px; border-radius: 3px; }"
                "QPushButton:disabled { background-color: #2a4a37; color: #aaa; }"
            )
        else:
            self._magnets_btn.setText("Magnets …")
            self._magnets_btn.setStyleSheet(
                "QPushButton { background-color: #555; color: #ddd;"
                " padding: 4px 10px; border-radius: 3px; }"
            )

    def _on_magnets_clicked(self) -> None:
        if self._client is None:
            return
        if self._magnets_state is True:
            # Currently enabled -> Kill.
            reply = QMessageBox.question(
                self, "Kill magnets?",
                "Immediately kill magnet power?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                result = self._client.disable_magnets()
                self._report_action_result("Kill Magnets", result)
            except Exception as exc:
                QMessageBox.warning(self, "Kill failed", repr(exc))
        elif self._magnets_state is False:
            # Currently off -> Enable.
            reply = QMessageBox.question(
                self, "Enable magnets?",
                "Re-enable magnet power?\n"
                "Make sure PLC is OK and cooling is verified before proceeding.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                result = self._client.enable_magnets()
                self._report_action_result("Enable Magnets", result)
            except Exception as exc:
                QMessageBox.warning(self, "Enable failed", repr(exc))

    def _report_action_result(self, label: str, result: dict) -> None:
        status = (result or {}).get("status", "error")
        if status == "ok":
            return  # status pill will update via next snapshot
        reason = result.get("reason") or result.get("message") or "?"
        QMessageBox.information(self, label, f"{status}: {reason}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_app_state(self, state) -> None:
        # IT13: on suspend, force unknown; on activate, the next snapshot will refresh.
        try:
            if state == Qt.ApplicationState.ApplicationSuspended:
                self._apply_status_style(_sm.STATE_UNKNOWN, "suspended")
                if self._poller is not None:
                    self._poller.force_unknown()
        except Exception:
            _LOG.exception("applicationStateChanged handler")

    def cleanup(self) -> None:
        try:
            if self._poller is not None:
                self._poller.stop()
        except Exception:
            pass
        auto_cleanup_timers(self)


class InterlockPanel(_InterlockBodyBase):
    """Server-side panel with control buttons."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(read_only=False, parent=parent)


class InterlockClientPanel(_InterlockBodyBase):
    """Client-side panel (read-only)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(read_only=True, parent=parent)


__all__ = ["InterlockPanel", "InterlockClientPanel"]
