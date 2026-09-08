"""
Live-adjust panel for the liveOD GUI.

AdjustPanel hosts one AdjustParamRow per adjustable parameter registered with
``self.adjust()`` in an experiment's ``prepare()``.  Each row shows a checkbox,
a spinbox, a reset button (↺) to revert to the default value, and a cog button
to edit min/max/step bounds.  Only checked rows are included in "Copy params";
the check-all/uncheck-all button toggles them in bulk, and clicking a param's
name copies just its assignment prefix ("self.p.key = ").
"""

import re
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QClipboard, QValidator
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


_SCI_RE = re.compile(r'^-?[0-9]*\.?[0-9]*([eE][+-]?[0-9]*)?$')


class ScientificDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that displays values in :.3e scientific notation."""

    def textFromValue(self, value: float) -> str:
        if 1.e-3 <= abs(value) <= 10:
            return f"{value:.3f}"
        return f"{value:.3e}"

    def valueFromText(self, text: str) -> float:
        try:
            return float(text)
        except ValueError:
            return self.minimum()

    def validate(self, text: str, pos: int):
        stripped = text.strip()
        try:
            float(stripped)
            return QValidator.State.Acceptable, text, pos
        except ValueError:
            if stripped in ('', '-') or _SCI_RE.match(stripped):
                return QValidator.State.Intermediate, text, pos
            return QValidator.State.Invalid, text, pos


class AdjustSpecDialog(QDialog):
    """Modal dialog for editing the min, max, and step of one adjust spec."""

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.spec = dict(spec)
        self._is_int = spec.get('dtype') == 'int'
        self.setWindowTitle(f"Adjust spec: {spec['key']}")
        self.setModal(True)

        layout = QFormLayout(self)

        initial_step = float(spec.get('step', 1.0))
        step_sb_step = max(1, int(initial_step // 20)) if self._is_int else initial_step / 20

        def make_spin(value, min_v=None, max_v=None, single_step=None):
            if self._is_int:
                sb = QSpinBox()
                sb.setRange(int(min_v) if min_v is not None else -2_000_000_000,
                            int(max_v) if max_v is not None else  2_000_000_000)
                sb.setValue(int(round(value)))
                if single_step is not None:
                    sb.setSingleStep(max(1, int(single_step)))
            else:
                sb = ScientificDoubleSpinBox()
                sb.setDecimals(6)
                sb.setRange(float(min_v) if min_v is not None else -1e18,
                            float(max_v) if max_v is not None else  1e18)
                sb.setSingleStep(float(single_step) if single_step is not None else initial_step)
                sb.setValue(float(value))
            return sb

        self._min_sb  = make_spin(spec['min_val'])
        self._max_sb  = make_spin(spec['max_val'])
        # step lower bound: 0 for float (functionally > 0 but hard to enforce), 1 for int
        # step spinbox increments at 1/20 of the initial step size
        self._step_sb = make_spin(spec['step'],
                                  min_v=1 if self._is_int else 0,
                                  single_step=step_sb_step)
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


class ClickableLabel(QLabel):
    """QLabel that emits ``clicked`` on a left-button press."""

    clicked = pyqtSignal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AdjustParamRow(QWidget):
    """One row: checkbox | key label | spinbox | reset | cog.

    The checkbox controls whether this row is included in "Copy params".
    Clicking the key label copies an assignment line prefix for that param.
    The reset button (↺) reverts to the value present when adjust() was called.

    While the spinbox is being typed into, remote value updates (which arrive at
    the start of every shot) are ignored so an in-progress edit is not clobbered;
    the edited value is only published once the edit is finished (Enter or focus
    loss), so the experiment keeps using the last edited value until then.
    """

    value_changed = pyqtSignal(str, float)               # key, new_value
    spec_updated  = pyqtSignal(str, float, float, float)  # key, min, max, step
    name_clicked  = pyqtSignal(str)                      # key
    check_toggled = pyqtSignal()

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.spec = dict(spec)
        self.key  = spec['key']
        self._is_int = spec.get('dtype') == 'int'
        self._default_val = float(spec['current_val'])
        self._editing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Checkbox ---
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(True)
        self._checkbox.setToolTip("Include in 'Copy params'")
        self._checkbox.toggled.connect(lambda _: self.check_toggled.emit())
        layout.addWidget(self._checkbox)

        lbl = ClickableLabel(self.key)
        lbl.setMinimumWidth(140)
        lbl.setToolTip("Click to copy this param's assignment prefix to the clipboard")
        lbl.clicked.connect(lambda: self.name_clicked.emit(self.key))
        layout.addWidget(lbl)

        # --- Spinbox ---
        if self._is_int:
            self._spinbox = QSpinBox()
            self._spinbox.setRange(int(spec['min_val']), int(spec['max_val']))
            self._spinbox.setSingleStep(max(1, int(spec['step'])))
            self._spinbox.setValue(int(round(spec['current_val'])))
        else:
            self._spinbox = ScientificDoubleSpinBox()
            self._spinbox.setDecimals(6)
            self._spinbox.setRange(float(spec['min_val']), float(spec['max_val']))
            self._spinbox.setSingleStep(float(spec['step']))
            self._spinbox.setValue(float(spec['current_val']))
        # only publish typed values once the edit is committed (Enter / focus out)
        self._spinbox.setKeyboardTracking(False)
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)
        self._spinbox.editingFinished.connect(self._on_editing_finished)
        line_edit = self._spinbox.lineEdit()
        if line_edit is not None:
            line_edit.textEdited.connect(self._on_text_edited)
        layout.addWidget(self._spinbox)

        # --- Reset button ---
        reset_btn = QPushButton("↺")
        reset_btn.setFixedWidth(30)
        reset_btn.setToolTip(f"Revert to default ({self._default_val})")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        # --- Cog button ---
        cog = QPushButton("⚙")
        cog.setFixedWidth(30)
        cog.setToolTip("Edit min / max / step")
        cog.clicked.connect(self._on_cog_clicked)
        layout.addWidget(cog)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_spinbox_changed(self, v):
        self._editing = False
        self.value_changed.emit(self.key, float(v))

    def _on_text_edited(self, _text):
        """User is typing into the spinbox -- hold off remote updates."""
        self._editing = True

    def _on_editing_finished(self):
        """Enter pressed or focus lost -- the edit is committed."""
        self._editing = False

    def _on_reset(self):
        """Revert spinbox to the default value."""
        self._editing = False
        if self._is_int:
            self._spinbox.setValue(int(round(self._default_val)))
        else:
            self._spinbox.setValue(self._default_val)
        # _on_spinbox_changed fires and emits value_changed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_editing(self) -> bool:
        """True while the user is typing a new value into the spinbox."""
        return self._editing

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool):
        self._checkbox.setChecked(bool(checked))

    def value(self):
        return self._spinbox.value()

    def update_value(self, value: float):
        """Update spinbox without triggering value_changed (remote sync).

        Ignored while the user is mid-edit so a shot starting does not reset the
        spinbox out from under them.
        """
        if self._editing:
            return
        self._spinbox.blockSignals(True)
        if self._is_int:
            self._spinbox.setValue(int(round(value)))
        else:
            self._spinbox.setValue(float(value))
        self._spinbox.blockSignals(False)

    def apply_spec(self, min_val: float, max_val: float, step: float):
        """Update range/step on the spinbox (called after cog dialog)."""
        self.spec.update({'min_val': min_val, 'max_val': max_val, 'step': step})
        if self._is_int:
            self._spinbox.setRange(int(min_val), int(max_val))
            self._spinbox.setSingleStep(max(1, int(step)))
        else:
            self._spinbox.setRange(min_val, max_val)
            self._spinbox.setSingleStep(step)

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

        # --- Copy group box ---
        copy_group = QGroupBox()
        group_layout = QHBoxLayout(copy_group)
        group_layout.setContentsMargins(4, 4, 4, 4)

        self._expt_params_btn = QPushButton(".p")
        self._expt_params_btn.setCheckable(True)
        self._expt_params_btn.setChecked(True)
        self._expt_params_btn.setFixedWidth(36)
        self._expt_params_btn.setToolTip(
            "When checked, copies 'self.p.key = value'; "
            "when unchecked, copies 'self.key = value'"
        )
        group_layout.addWidget(self._expt_params_btn)

        self._copy_btn = QPushButton("Copy params")
        self._copy_btn.setToolTip(
            "Copy all current adjust values as assignment lines"
        )
        self._copy_btn.clicked.connect(self._copy_params_to_clipboard)
        group_layout.addWidget(self._copy_btn)

        self._check_all_btn = QPushButton("Uncheck all")
        self._check_all_btn.setToolTip(
            "Uncheck (or check) every param's 'Copy params' checkbox"
        )
        self._check_all_btn.clicked.connect(self._on_check_all_clicked)
        group_layout.addWidget(self._check_all_btn)

        # Scroll area so many params don't overflow the window
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._row_layout = QVBoxLayout(container)
        self._row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.addWidget(copy_group)
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
                row.name_clicked.disconnect()
                row.check_toggled.disconnect()
            except Exception:
                pass
            self._row_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        for spec in specs:
            row = AdjustParamRow(spec, self)
            row.value_changed.connect(self.value_changed_signal)
            row.spec_updated.connect(self.spec_updated_signal)
            row.name_clicked.connect(self._copy_key_prefix_to_clipboard)
            row.check_toggled.connect(self._update_check_all_button)
            self._rows[spec['key']] = row
            self._row_layout.addWidget(row)
        self._update_check_all_button()

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

    def _assignment_prefix(self, key: str) -> str:
        """'self.p.key = ' or 'self.key = ', per the .p toggle."""
        if self._expt_params_btn.isChecked():
            return f"self.p.{key} = "
        return f"self.{key} = "

    def _copy_key_prefix_to_clipboard(self, key: str):
        """Copy just the assignment prefix for one param (clicked key label)."""
        QApplication.clipboard().setText(self._assignment_prefix(key))

    def _on_check_all_clicked(self):
        """Uncheck every row, or check them all if none are checked."""
        target = not any(row.is_checked() for row in self._rows.values())
        for row in self._rows.values():
            row.set_checked(target)
        self._update_check_all_button()

    def _update_check_all_button(self):
        """Label the button by what it will do next."""
        any_checked = any(row.is_checked() for row in self._rows.values())
        self._check_all_btn.setText("Uncheck all" if any_checked else "Check all")

    def _copy_params_to_clipboard(self):
        """Copy checked adjust values as assignment lines to the clipboard."""
        indent = "        "  # two leading indents (8 spaces)
        lines = []
        for key, row in self._rows.items():
            if not row.is_checked():
                continue
            lines.append(f"{self._assignment_prefix(key)}{row.value()}")
        if lines:
            text = lines[0] + ("\n" + "\n".join(indent + l for l in lines[1:]) if len(lines) > 1 else "")
        else:
            text = ""
        QApplication.clipboard().setText(text)
