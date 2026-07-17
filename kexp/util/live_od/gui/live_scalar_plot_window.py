"""
Live per-shot scalar plot window for liveOD.

Receives per-shot scalar dicts via ``shot_scalars_signal`` and plots the
selected metric vs shot index or the current xvar value (with correct unit
scaling via ``detect_unit``).

Both the local liveOD window and the remote viewer window use this widget.
"""

import collections
import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Metric registry
# ---------------------------------------------------------------------------

# (display_label, dict_key, y_multiplier, y_unit_str)
METRICS = [
    ("atom number",            "atom_number",            1.0,  ""),
    ("atom number fit area x", "atom_number_fit_area_x", 1.0,  ""),
    ("atom number fit area y", "atom_number_fit_area_y", 1.0,  ""),
    ("fit σ x",                "fit_sd_x",               1e6,  "µm"),
    ("fit σ y",                "fit_sd_y",               1e6,  "µm"),
    ("fit amp x",              "fit_amp_x",              1.0,  "sum OD"),
    ("fit amp y",              "fit_amp_y",              1.0,  "sum OD"),
]

# Metrics that require Gaussian fits (vs those that only need integrated OD)
_FIT_KEYS = {
    "atom_number_fit_area_x",
    "atom_number_fit_area_y",
    "fit_sd_x",
    "fit_sd_y",
    "fit_amp_x",
    "fit_amp_y",
}


def _metric_tier(key: str) -> str:
    """Return the compute tier ('atom_number' or 'fits') for a metric key."""
    return "fits" if key in _FIT_KEYS else "atom_number"


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class LiveScalarPlotWindow(QWidget):
    """Popup window: live per-shot scalar plot.

    Signals
    -------
    subscription_changed_signal(old_tier, new_tier)
        Emitted when the required compute tier changes due to a metric
        switch, window show, or window close.  ``old_tier`` and/or
        ``new_tier`` may be ``None`` (window appearing / disappearing).
    """

    subscription_changed_signal = pyqtSignal(object, object)  # old_tier, new_tier

    MAX_STORED_SHOTS = 10_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Scalar Plot")
        self.resize(720, 460)

        self._data: collections.deque = collections.deque(maxlen=self.MAX_STORED_SHOTS)
        self._xvarnames: list = []
        self._current_run_id: int = 0
        # Per-xvar unit cache: xvarname -> (unit_str, mult)
        self._unit_cache: dict = {}
        # Track whether we are currently subscribed (for show/hide transitions)
        self._subscribed_tier: str | None = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Control row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        ctrl.addWidget(QLabel("Metric:"))
        self.metric_combo = QComboBox()
        for label, *_ in METRICS:
            self.metric_combo.addItem(label)
        self.metric_combo.currentIndexChanged.connect(self._on_metric_changed)
        ctrl.addWidget(self.metric_combo)

        ctrl.addWidget(QLabel("X axis:"))
        self.xaxis_combo = QComboBox()
        self.xaxis_combo.addItem("shot index")
        self.xaxis_combo.currentIndexChanged.connect(self._refresh_plot)
        ctrl.addWidget(self.xaxis_combo)

        ctrl.addWidget(QLabel("Last N:"))
        self.n_shots_spin = QSpinBox()
        self.n_shots_spin.setRange(1, self.MAX_STORED_SHOTS)
        self.n_shots_spin.setValue(200)
        self.n_shots_spin.valueChanged.connect(self._refresh_plot)
        ctrl.addWidget(self.n_shots_spin)

        self.show_all_check = QCheckBox("show all")
        self.show_all_check.stateChanged.connect(self._on_show_all_changed)
        ctrl.addWidget(self.show_all_check)

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._on_clear)
        ctrl.addWidget(self.clear_button)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # Plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._scatter_item = pg.ScatterPlotItem(
            size=5, brush=pg.mkBrush(100, 180, 255, 200)
        )
        self.plot_widget.addItem(self._scatter_item)
        layout.addWidget(self.plot_widget)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def on_shot_scalars(self, scalars: dict):
        """Receive a per-shot scalar dict from Analyzer or ZMQ subscriber."""
        self._data.append(scalars)
        self._refresh_plot()

    def on_new_run(self, run_id: int, xvarnames: list):
        """Called at the start of each run to reset data and update x-axis choices."""
        self._current_run_id = run_id
        self._data.clear()
        self._unit_cache.clear()
        self.setWindowTitle(f"Live Scalar Plot — run {run_id}")

        # Repopulate x-axis dropdown, preserving previous selection if valid
        prev = self.xaxis_combo.currentText()
        self.xaxis_combo.blockSignals(True)
        self.xaxis_combo.clear()
        self.xaxis_combo.addItem("shot index")
        self._xvarnames = list(xvarnames)
        for name in xvarnames:
            self.xaxis_combo.addItem(name)
        idx = self.xaxis_combo.findText(prev)
        self.xaxis_combo.setCurrentIndex(max(0, idx))
        self.xaxis_combo.blockSignals(False)

        self._refresh_plot()

    # ------------------------------------------------------------------
    # Qt event overrides (subscription lifecycle)
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        new_tier = self._current_tier()
        if self._subscribed_tier != new_tier:
            self.subscription_changed_signal.emit(self._subscribed_tier, new_tier)
            self._subscribed_tier = new_tier

    def closeEvent(self, event):
        old_tier = self._subscribed_tier
        self._subscribed_tier = None
        if old_tier is not None:
            self.subscription_changed_signal.emit(old_tier, None)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_tier(self) -> str:
        key = METRICS[self.metric_combo.currentIndex()][1]
        return _metric_tier(key)

    def _on_metric_changed(self, _idx):
        new_tier = self._current_tier()
        if self.isVisible() and self._subscribed_tier != new_tier:
            self.subscription_changed_signal.emit(self._subscribed_tier, new_tier)
            self._subscribed_tier = new_tier
        self._refresh_plot()

    def _on_show_all_changed(self, state):
        self.n_shots_spin.setEnabled(not bool(state))
        self._refresh_plot()

    def _on_clear(self):
        self._data.clear()
        self._unit_cache.clear()
        self._scatter_item.setData([], [])
        self.plot_widget.setTitle("")

    def _get_x_unit(self, xvarname: str, values) -> tuple:
        """Return ``(unit_str, mult)`` for *xvarname* using detect_unit with fallback.

        Caches the result per xvarname once ≥3 values are available (the
        magnitude-based ``guess_unit`` heuristic needs actual values to pick
        the right prefix).
        """
        if xvarname in self._unit_cache:
            return self._unit_cache[xvarname]

        result = ("", 1.0)
        finite = [v for v in values if math.isfinite(v)]
        if len(finite) >= 3:
            try:
                from waxa.plotting.plotting_1d import detect_unit
                unit, mult, _ = detect_unit(
                    xvarnames=[xvarname],
                    xvar_idx=0,
                    xvar_values=np.asarray(finite, dtype=float),
                )
                result = (unit or "", mult if mult else 1.0)
            except Exception:
                pass
            self._unit_cache[xvarname] = result

        return result

    def _refresh_plot(self):
        if not self._data:
            self._scatter_item.setData([], [])
            return

        # Slice to requested window
        if self.show_all_check.isChecked():
            data = list(self._data)
        else:
            n = self.n_shots_spin.value()
            data = list(self._data)[-n:]

        metric_idx = self.metric_combo.currentIndex()
        _label, key, ymult, yunit = METRICS[metric_idx]
        xaxis_sel = self.xaxis_combo.currentText()

        # Build (x, y) pairs, skipping any NaN/None y values
        xs, ys = [], []
        for d in data:
            y_raw = d.get(key)
            if y_raw is None:
                continue
            y_val = float(y_raw) * ymult
            if not math.isfinite(y_val):
                continue
            if xaxis_sel == "shot index":
                x_val = float(d.get("shot_idx", 0))
            else:
                xvar_vals = d.get("xvar_values", {})
                raw_x = xvar_vals.get(xaxis_sel)
                if raw_x is None:
                    continue
                x_val = float(raw_x)
                if not math.isfinite(x_val):
                    continue
            xs.append(x_val)
            ys.append(y_val)

        if not xs:
            self._scatter_item.setData([], [])
            return

        x_arr = np.array(xs, dtype=float)
        y_arr = np.array(ys, dtype=float)

        # X-axis unit scaling
        xlabel = "shot index"
        if xaxis_sel != "shot index":
            unit, xmult = self._get_x_unit(xaxis_sel, xs)
            x_arr = x_arr * xmult
            xlabel = f"{xaxis_sel} ({unit})" if unit else xaxis_sel

        ylabel = f"{_label} ({yunit})" if yunit else _label

        self._scatter_item.setData(x_arr, y_arr)
        self.plot_widget.setLabel("bottom", xlabel)
        self.plot_widget.setLabel("left", ylabel)

        n_skipped = len(data) - len(xs)
        title = f"run {self._current_run_id}"
        if n_skipped > 0:
            title += f"  ({n_skipped} NaN skipped)"
        self.plot_widget.setTitle(title)
