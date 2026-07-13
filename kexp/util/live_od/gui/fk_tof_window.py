"""
FK TOF — Fast-Kinetics Time-of-Flight live analysis window.

When N_pwa_per_shot > 1 with absorption imaging, each shot produces multiple
probe-with-atoms (PWA) images sharing one light and one dark reference.
This window receives per-shot Gaussian widths (sigma_x, sigma_y, one per PWA)
from the Analyzer, builds a time axis from user-specified t0 and dt, fits a
GaussianTemperatureFit to sigma(t), and displays the resulting temperature live.
"""

import re
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

_KEY_RE = re.compile(r'^[A-Za-z_]\w*$')   # valid Python identifier / param key


def _parse_time_input(text: str, params: dict) -> tuple:
    """Parse a t0/dt input string.

    Accepts:
      - A plain float literal (e.g. ``"100e-6"``) → returns (value_s, None)
      - A valid param key (letters/numbers/underscores, starts with letter or
        underscore) that exists in params and resolves to a finite scalar
        → returns (value_s, None)

    Returns:
      (value_in_seconds: float, error_message: str | None)
      On success, error_message is None.  On failure, value_in_seconds is nan.
    """
    text = text.strip()
    if not text:
        return float('nan'), "empty"
    # Try numeric first
    try:
        val = float(text)
        if np.isfinite(val):
            return val, None
    except ValueError:
        pass
    # Try as param key
    if _KEY_RE.match(text):
        if text in params:
            raw = params[text]
            try:
                val = float(raw)
                if np.isfinite(val):
                    return val, None
                return float('nan'), f"params['{text}'] = {raw!r} is not finite"
            except (TypeError, ValueError):
                return float('nan'), f"params['{text}'] = {raw!r} is not a number"
        return float('nan'), f"key '{text}' not found in params"
    return float('nan'), "invalid: not a number or param key"


class FkTofWindow(QWidget):
    """Standalone popup that fits temperature from per-PWA widths.

    Receives data via ``on_pwa_data(data)`` slot after each analyzed shot.
    ``data`` is a dict with keys:
        sigma_x : list[float]  — per-PWA Gaussian width in x (meters)
        sigma_y : list[float]  — per-PWA Gaussian width in y (meters)
        shot_idx : int
        N_pwa   : int
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FK TOF — Fast Kinetics TOF")
        self.resize(600, 480)

        self._params: dict = {}
        self._current_run_id: int = 0
        self._last_data: dict | None = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Control row ---
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        ctrl.addWidget(QLabel("t\u2080 (s or key):"))
        self.t0_edit = QLineEdit("100e-6")
        self.t0_edit.setPlaceholderText("e.g. 100e-6 or t_first_image")
        self.t0_edit.setMaximumWidth(140)
        self.t0_edit.textChanged.connect(self._on_input_changed)
        ctrl.addWidget(self.t0_edit)

        ctrl.addWidget(QLabel("\u0394t (s or key):"))
        self.dt_edit = QLineEdit("50e-6")
        self.dt_edit.setPlaceholderText("e.g. 50e-6 or t_between_images")
        self.dt_edit.setMaximumWidth(140)
        self.dt_edit.textChanged.connect(self._on_input_changed)
        ctrl.addWidget(self.dt_edit)

        ctrl.addWidget(QLabel("Axis:"))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["x", "y"])
        self.axis_combo.currentIndexChanged.connect(self._on_input_changed)
        ctrl.addWidget(self.axis_combo)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # --- Status label ---
        self.status_label = QLabel("No data yet.")
        self.status_label.setStyleSheet("color: grey; font-size: 11px;")
        layout.addWidget(self.status_label)

        # --- Plot ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel("bottom", "time (\u00b5s)")
        self.plot_widget.setLabel("left", "\u03c3 (\u00b5m)")
        self._scatter_item = pg.ScatterPlotItem(
            size=9, brush=pg.mkBrush(255, 160, 40, 220), pen=pg.mkPen(None)
        )
        self._fit_line = self.plot_widget.plot(
            [], [], pen=pg.mkPen("c", width=2)
        )
        self.plot_widget.addItem(self._scatter_item)
        layout.addWidget(self.plot_widget, stretch=1)

        # --- Temperature result label ---
        self.temp_label = QLabel("T = \u2014")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self.temp_label.setFont(font)
        self.temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.temp_label)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Public slots / API
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def on_pwa_data(self, data: dict):
        """Receive per-shot PWA width data from the Analyzer."""
        self._last_data = data
        self._refit_and_plot()

    def on_new_run(self, run_id: int, params: dict):
        """Called at the start of each run with params payload."""
        self._current_run_id = run_id
        self._params = dict(params) if params else {}
        self._last_data = None
        self.setWindowTitle(f"FK TOF \u2014 run {run_id}")
        self._scatter_item.setData([], [])
        self._fit_line.setData([], [])
        self.temp_label.setText("T = \u2014")
        self.status_label.setText(f"Run {run_id} started. Waiting for shots\u2026")
        self.status_label.setStyleSheet("color: grey; font-size: 11px;")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_input_changed(self):
        if self._last_data is not None:
            self._refit_and_plot()

    def _refit_and_plot(self):
        data = self._last_data
        if data is None:
            return

        t0, err0 = _parse_time_input(self.t0_edit.text(), self._params)
        dt, errdt = _parse_time_input(self.dt_edit.text(), self._params)

        if err0 or errdt:
            errmsg = " | ".join(m for m in [err0, errdt] if m)
            self.status_label.setText(f"\u26a0 {errmsg}")
            self.status_label.setStyleSheet("color: orange; font-size: 11px;")
            return

        axis = self.axis_combo.currentText()   # "x" or "y"
        sigmas_m = np.array(data[f'sigma_{axis}'], dtype=float)
        N_pwa = len(sigmas_m)

        if N_pwa < 3:
            self.status_label.setText(
                f"\u26a0 Need \u2265 3 PWA images for fit; got {N_pwa}."
            )
            self.status_label.setStyleSheet("color: orange; font-size: 11px;")
            return

        # Build time axis (seconds)
        t_s = t0 + np.arange(N_pwa) * dt

        # Choose display units for time axis
        if t_s[-1] >= 1e-3:
            t_mult, t_unit = 1e3, "ms"
        else:
            t_mult, t_unit = 1e6, "\u00b5s"

        # Fit
        try:
            from waxa.fitting.gaussian import GaussianTemperatureFit
            import kamo.constants as c
            fit = GaussianTemperatureFit(t_s, sigmas_m)
            T = float(fit.T)
            err_T = float(fit.err_T)

            # Evaluate fit on dense grid using the same model as GaussianTemperatureFit
            t_dense = np.linspace(t_s[0], t_s[-1], 300)
            y_dense_sq = (
                c.kB * T / c.m_K * (t_dense * fit._mult) ** 2
                + (fit.sigma0 * fit._mult) ** 2
            )
            y_dense_m = np.sqrt(np.maximum(y_dense_sq, 0)) / fit._mult
        except Exception as e:
            self.status_label.setText(f"Fit failed: {e}")
            self.status_label.setStyleSheet("color: red; font-size: 11px;")
            self._scatter_item.setData(t_s * t_mult, sigmas_m * 1e6)
            self._fit_line.setData([], [])
            self.temp_label.setText("T = fit error")
            return

        # Choose temperature display units
        if T >= 1e-3:
            T_mult, T_prefix = 1e3, "m"
        elif T >= 1e-6:
            T_mult, T_prefix = 1e6, "\u00b5"
        else:
            T_mult, T_prefix = 1e9, "n"

        # Update plot
        self._scatter_item.setData(t_s * t_mult, sigmas_m * 1e6)
        self._fit_line.setData(t_dense * t_mult, y_dense_m * 1e6)
        self.plot_widget.setLabel("bottom", f"time ({t_unit})")
        self.plot_widget.setLabel("left", f"\u03c3_{axis} (\u00b5m)")

        shot_idx = data.get('shot_idx', '?')
        self.status_label.setText(
            f"shot {shot_idx} | run {self._current_run_id} | "
            f"N_pwa={N_pwa} | "
            f"t\u2080={t0 * 1e6:.1f} \u00b5s | \u0394t={dt * 1e6:.1f} \u00b5s"
        )
        self.status_label.setStyleSheet("color: grey; font-size: 11px;")
        self.temp_label.setText(
            f"T = {T * T_mult:.3g} \u00b1 {err_T * T_mult:.1f} {T_prefix}K"
        )
