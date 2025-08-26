import sys
import json
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QGridLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QMessageBox, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt

from kexp.config import dds_id, ttl_id, dac_id
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.TTL import TTL
from kexp.control.artiq.DAC_CH import DAC_CH

# DEVICE_STATE_PATH = "c:/Users/bananas/code/k-exp/kexp/util/device_state/device_state_config.json"
import os
DEVICE_STATE_PATH = os.path.join(os.getenv('code'),'kexp','kexp','util','device_state','device_state_config.json')
TTL_IGNORE_RANGE = range(40, 48)
DAC_MAX_VOLTAGE = 9.99  # Example, replace with per-channel value if available

def safe_update_device_state(data):
    for _ in range(100):
        try:
            with open(DEVICE_STATE_PATH, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            time.sleep(0.05)
    return False

def safe_read_device_state():
    for _ in range(100):
        try:
            with open(DEVICE_STATE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            time.sleep(0.05)
    return {}

class DDSChannelWidget(QWidget):
    def __init__(self, dds_obj, key):
        super().__init__()
        layout = QGridLayout()
        layout.addWidget(QLabel(f"Key: {key}"), 0, 0)

        self.freq_edit = QLineEdit(str(dds_obj.frequency))
        layout.addWidget(QLabel("Frequency:"), 0, 1)
        layout.addWidget(self.freq_edit, 0, 2)

        if getattr(dds_obj, "transition", None) != "None":
            self.unit_combo = QComboBox()
            self.unit_combo.addItems(["Hz", "Linewidth"])
            layout.addWidget(self.unit_combo, 0, 3)
            self.unit_combo.currentTextChanged.connect(self.unit_changed)
        else:
            self.unit_combo = None

        self.amp_edit = QLineEdit(str(dds_obj.amplitude))
        layout.addWidget(QLabel("Amplitude:"), 1, 1)
        layout.addWidget(self.amp_edit, 1, 2)

        if getattr(dds_obj, "dac_ch", -1) != -1:
            self.amp_mode_combo = QComboBox()
            self.amp_mode_combo.addItems(["Amplitude", "v_pd"])
            layout.addWidget(self.amp_mode_combo, 1, 3)
        else:
            self.amp_mode_combo = None

        self.submit_btn = QPushButton("Submit")
        self.toggle_btn = QPushButton("Toggle Switch")
        layout.addWidget(self.submit_btn, 2, 1)
        layout.addWidget(self.toggle_btn, 2, 2)

        self.setLayout(layout)
        self.submit_btn.clicked.connect(self.submit)
        self.toggle_btn.clicked.connect(self.toggle)

        self.dds_obj = dds_obj
        self.key = key

    def unit_changed(self, unit):
        try:
            if unit == "Linewidth":
                freq = float(self.freq_edit.text())
                detuning = self.dds_obj.frequency_to_detuning(freq)
                self.freq_edit.setText(str(detuning))
            else:
                detuning = float(self.freq_edit.text())
                freq = self.dds_obj.detuning_to_frequency(detuning)
                self.freq_edit.setText(str(freq))
        except Exception as e:
            QMessageBox.warning(self, "Conversion Error", str(e))

    def submit(self):
        try:
            freq = float(self.freq_edit.text())
            amp = float(self.amp_edit.text())
            amp_mode = self.amp_mode_combo.currentText() if self.amp_mode_combo else "Amplitude"
            unit = self.unit_combo.currentText() if self.unit_combo else "Hz"
            state = safe_read_device_state()
            if "dds" not in state:
                state["dds"] = {}
            state["dds"][self.key] = {
                "frequency": freq,
                "amplitude": amp,
                "amp_mode": amp_mode,
                "unit": unit,
                "switch": getattr(self.dds_obj, "switch", False)
            }
            if not safe_update_device_state(state):
                QMessageBox.warning(self, "File Error", "Could not update device state config file.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def toggle(self):
        try:
            state = safe_read_device_state()
            if "dds" not in state:
                state["dds"] = {}
            current = state["dds"].get(self.key, {}).get("switch", False)
            state["dds"][self.key] = state["dds"].get(self.key, {})
            state["dds"][self.key]["switch"] = not current
            if not safe_update_device_state(state):
                QMessageBox.warning(self, "File Error", "Could not update device state config file.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

class TTLChannelWidget(QWidget):
    def __init__(self, key):
        super().__init__()
        layout = QHBoxLayout()
        layout.addWidget(QLabel(f"TTL {key}"))
        self.toggle_btn = QPushButton("Toggle")
        layout.addWidget(self.toggle_btn)
        self.setLayout(layout)
        self.toggle_btn.clicked.connect(self.toggle)
        self.key = key

    def toggle(self):
        try:
            state = safe_read_device_state()
            if "ttl" not in state:
                state["ttl"] = {}
            current = state["ttl"].get(str(self.key), False)
            state["ttl"][str(self.key)] = not current
            if not safe_update_device_state(state):
                QMessageBox.warning(self, "File Error", "Could not update device state config file.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

class DACChannelWidget(QWidget):
    def __init__(self, key, max_voltage=DAC_MAX_VOLTAGE):
        super().__init__()
        layout = QHBoxLayout()
        layout.addWidget(QLabel(f"DAC {key}"))
        self.voltage_edit = QLineEdit()
        layout.addWidget(self.voltage_edit)
        self.submit_btn = QPushButton("Submit")
        self.toggle_btn = QPushButton("Zero/Restore")
        layout.addWidget(self.submit_btn)
        layout.addWidget(self.toggle_btn)
        self.setLayout(layout)
        self.submit_btn.clicked.connect(self.submit)
        self.toggle_btn.clicked.connect(self.toggle)
        self.key = key
        self.max_voltage = max_voltage
        self.last_value = 0.0

    def submit(self):
        try:
            voltage = float(self.voltage_edit.text())
            if abs(voltage) > self.max_voltage:
                QMessageBox.warning(self, "Voltage Error", f"Voltage exceeds max ({self.max_voltage} V)!")
                return
            self.last_value = voltage
            state = safe_read_device_state()
            if "dac" not in state:
                state["dac"] = {}
            state["dac"][str(self.key)] = voltage
            if not safe_update_device_state(state):
                QMessageBox.warning(self, "File Error", "Could not update device state config file.")
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid voltage value.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def toggle(self):
        try:
            current_val = float(self.voltage_edit.text()) if self.voltage_edit.text() else 0.0
            if current_val != 0.0:
                self.voltage_edit.setText("0.0")
            else:
                self.voltage_edit.setText(str(self.last_value))
            # Update device state config
            voltage = float(self.voltage_edit.text())
            state = safe_read_device_state()
            if "dac" not in state:
                state["dac"] = {}
            state["dac"][str(self.key)] = voltage
            if not safe_update_device_state(state):
                QMessageBox.warning(self, "File Error", "Could not update device state config file.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Device State Control")
        tabs = QTabWidget()
        tabs.addTab(self.create_dds_tab(), "DDS Channels")
        tabs.addTab(self.create_ttl_tab(), "TTL Channels")
        tabs.addTab(self.create_dac_tab(), "DAC Channels")
        self.setCentralWidget(tabs)

    def create_dds_tab(self):
        widget = QWidget()
        layout = QGridLayout()
        # Only include keys that do not start with '_'
        dds_keys = [key for key in self.__dict__.keys() if isinstance(self.__dict__[key], DDS) and not key.startswith('_')]
        for idx, key in enumerate(dds_keys):
            dds_obj = dds_id[key]
            urukul_idx = getattr(dds_obj, "urukul_idx", 0)
            ch = getattr(dds_obj, "ch", idx)
            layout.addWidget(DDSChannelWidget(dds_obj, key), ch, urukul_idx)
        widget.setLayout(layout)
        return widget

    def create_ttl_tab(self):
        widget = QWidget()
        layout = QGridLayout()
        ttl_keys = [k for k in ttl_id if not str(k).startswith('_')]
        row = 0
        for key in ttl_keys:
            if isinstance(key, int) and key in TTL_IGNORE_RANGE:
                continue
            layout.addWidget(TTLChannelWidget(key), row // 8, row % 8)
            row += 1
        widget.setLayout(layout)
        return widget

    def create_dac_tab(self):
        widget = QWidget()
        layout = QGridLayout()
        dac_keys = [k for k in dac_id if not str(k).startswith('_')]
        row = 0
        for key in dac_keys:
            layout.addWidget(DACChannelWidget(key), row // 8, row % 8)
            row += 1
        widget.setLayout(layout)
        return widget

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())