"""
Live-adjust panel for the liveOD GUI.

AdjustPanel hosts one AdjustParamRow per adjustable parameter registered with
``self.adjust()`` in an experiment's ``prepare()``.  Each row contains a
spinbox that updates ``self.params`` on the host before the next shot.  A cog
button opens AdjustSpecDialog to change the spinbox min/max/step and sync the
new bounds back to the server.
"""

import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Number of discrete steps the slider uses to cover the [min, max] range.
# Higher = finer float resolution at the cost of slider thumb sensitivity.
_N_SLIDER_STEPS = 1000


class AdjustSpecDialog(QDialog):
    """Modal dialog for editing the min, max, and step of one adjust spec."""

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.spec = dict(spec)
        self._is_int = spec.get('dtype') == 'int'
        self.setWindowTitle(f"Adjust spec: {spec['key']}")
        self.setModal(True)

        layout = QFormLayout(self)

        def make_spin(value, min_v=None, max_v=None):
            if self._is_int:
                sb = QSpinBox()
                sb.setRange(int(min_v) if min_v is not None else -2_000_000_000,
                            int(max_v) if max_v is not None else  2_000_000_000)
                sb.setValue(int(round(value)))
            else:
                sb = QDoubleSpinBox()
                sb.setDecimals(6)
                sb.setRange(float(min_v) if min_v is not None else -1e18,
                            float(max_v) if max_v is not None else  1e18)
                sb.setSingleStep(float(spec.get('step', 1.0)))
                sb.setValue(float(value))
            return sb

        self._min_sb  = make_spin(spec['min_val'])
        self._max_sb  = make_spin(spec['max_val'])
        # step lower bound: 0 for float (functionally > 0 but hard to enforce), 1 for int
        self._step_sb = make_spin(spec['step'],
                                  min_v=1 if self._is_int else 0)
        layout.addRow("Min", self._min_sb)
        layout.addRow("Max", self._max_sb)
        layout.addRow("Step", self._step_sb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> tuple:
        """Return (min_val, max_val, step) as float."""
        return (
            float(self._min_sb.value()),
            float(self._max_sb.value()),
            float(self._step_sb.value()),
        )


class AdjustParamRow(QWidget):
    """One row: key label | value control (spinbox or slider) | toggle | cog.

    The toggle button switches the value control between an up/down spinbox
    and a horizontal slider.  Both widgets are kept in sync so toggling
    never changes the current value.
    """

    value_changed = pyqtSignal(str, float)          # key, new_value
    spec_updated  = pyqtSignal(str, float, float, float)  # key, min, max, step

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.spec = dict(spec)
        self.key  = spec['key']
        self._is_int = spec.get('dtype') == 'int'
        self._use_slider = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(self.key)
        lbl.setMinimumWidth(140)
        layout.addWidget(lbl)

        # --- Spinbox ---
        if self._is_int:
            self._spinbox = QSpinBox()
            self._spinbox.setRange(int(spec['min_val']), int(spec['max_val']))
            self._spinbox.setSingleStep(max(1, int(spec['step'])))
            self._spinbox.setValue(int(round(spec['current_val'])))
        else:
            self._spinbox = QDoubleSpinBox()
            self._spinbox.setDecimals(6)
            self._spinbox.setRange(float(spec['min_val']), float(spec['max_val']))
            self._spinbox.setSingleStep(float(spec['step']))
            self._spinbox.setValue(float(spec['current_val']))
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)
        layout.addWidget(self._spinbox, 1)

        # --- Slider (hidden by default) ---
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _N_SLIDER_STEPS)
        self._slider.setValue(self._val_to_slider(float(spec['current_val'])))
        self._slider.setVisible(False)
        self._slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider, 1)

        # --- Toggle button ---
        self._toggle_btn = QPushButton("━")
        self._toggle_btn.setFixedWidth(30)
        self._toggle_btn.setToolTip("Switch to slider")
        self._toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle_btn)

        # --- Cog button ---
        cog = QPushButton("⚙")
        cog.setFixedWidth(30)
        cog.setToolTip("Edit min / max / step")
        cog.clicked.connect(self._on_cog_clicked)
        layout.addWidget(cog)

    # ------------------------------------------------------------------
    # Slider ↔ value mapping
    # ------------------------------------------------------------------

    def _val_to_slider(self, value: float) -> int:
        min_v = float(self.spec['min_val'])
        max_v = float(self.spec['max_val'])
        if max_v == min_v:
            return 0
        frac = (value - min_v) / (max_v - min_v)
        return int(round(max(0.0, min(float(_N_SLIDER_STEPS), frac * _N_SLIDER_STEPS))))

    def _slider_to_val(self, pos: int) -> float:
        min_v = float(self.spec['min_val'])
        max_v = float(self.spec['max_val'])
        val = min_v + (pos / _N_SLIDER_STEPS) * (max_v - min_v)
        if self._is_int:
            return float(int(round(val)))
        return val

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_spinbox_changed(self, v):
        self._slider.blockSignals(True)
        self._slider.setValue(self._val_to_slider(float(v)))
        self._slider.blockSignals(False)
        self.value_changed.emit(self.key, float(v))

    def _on_slider_changed(self, pos: int):
        val = self._slider_to_val(pos)
        self._spinbox.blockSignals(True)
        if self._is_int:
            self._spinbox.setValue(int(round(val)))
        else:
            self._spinbox.setValue(val)
        self._spinbox.blockSignals(False)
        self.value_changed.emit(self.key, val)

    def _on_toggle(self):
        self._use_slider = not self._use_slider
        self._spinbox.setVisible(not self._use_slider)
        self._slider.setVisible(self._use_slider)
        if self._use_slider:
            self._toggle_btn.setText("⇅")
            self._toggle_btn.setToolTip("Switch to spinbox")
        else:
            self._toggle_btn.setText("━")
            self._toggle_btn.setToolTip("Switch to slider")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_value(self, value: float):
        """Update both widgets without triggering value_changed (remote sync)."""
        self._spinbox.blockSignals(True)
        self._slider.blockSignals(True)
        if self._is_int:
            self._spinbox.setValue(int(round(value)))
        else:
            self._spinbox.setValue(float(value))
        self._slider.setValue(self._val_to_slider(float(value)))
        self._spinbox.blockSignals(False)
        self._slider.blockSignals(False)

    def apply_spec(self, min_val: float, max_val: float, step: float):
        """Update range/step on both widgets (called after cog dialog)."""
        self.spec.update({'min_val': min_val, 'max_val': max_val, 'step': step})
        if self._is_int:
            self._spinbox.setRange(int(min_val), int(max_val))
            self._spinbox.setSingleStep(max(1, int(step)))
        else:
            self._spinbox.setRange(min_val, max_val)
            self._spinbox.setSingleStep(step)
        # Re-sync slider to current spinbox value under new range
        self._slider.blockSignals(True)
        self._slider.setValue(self._val_to_slider(float(self._spinbox.value())))
        self._slider.blockSignals(False)

    def _on_cog_clicked(self):
        dlg = AdjustSpecDialog(self.spec, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            min_v, max_v, step = dlg.get_values()
            self.apply_spec(min_v, max_v, step)
            self.spec_updated.emit(self.key, min_v, max_v, step)


class AdjustPanel(QWidget):
    """Panel with one AdjustParamRow per adjustable parameter.

    value_changed_signal is forwarded from individual rows.
    spec_updated_signal is forwarded from cog-dialog acceptances.
    """

    value_changed_signal = pyqtSignal(str, float)          # key, value
    spec_updated_signal  = pyqtSignal(str, float, float, float)  # key, min, max, step

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, AdjustParamRow] = {}

        # Scroll area so many params don't overflow the window
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._row_layout = QVBoxLayout(container)
        self._row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll)
        self.setMinimumWidth(340)
        self.setWindowTitle("Adjust Parameters")

    def populate(self, specs: list):
        """Rebuild rows from a list of spec dicts (called after INIT_RUN)."""
        # Disconnect old rows first
        for row in self._rows.values():
            try:
                row.value_changed.disconnect()
                row.spec_updated.disconnect()
            except Exception:
                pass
            self._row_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        for spec in specs:
            row = AdjustParamRow(spec, self)
            row.value_changed.connect(self.value_changed_signal)
            row.spec_updated.connect(self.spec_updated_signal)
            self._rows[spec['key']] = row
            self._row_layout.addWidget(row)

    def update_values(self, values: dict):
        """Update displayed values from a broadcast without emitting signals."""
        for key, val in values.items():
            row = self._rows.get(key)
            if row is not None:
                row.update_value(float(val))

    def apply_spec_update(self, key: str, min_val: float, max_val: float, step: float):
        """Apply an externally-sourced spec change to a row (e.g. from remote viewer)."""
        row = self._rows.get(key)
        if row is not None:
            row.apply_spec(min_val, max_val, step)
