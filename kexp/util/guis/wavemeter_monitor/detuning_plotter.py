import sys
import time
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import numpy as np
from kamo import Potassium39
from mogdevice import MOGDevice

# Use the existing atom and fzw variables from the notebook

class DetuningPlotter(QtWidgets.QWidget):
    def __init__(self, atom, fzw):
        super().__init__()
        self.atom = atom
        self.fzw = fzw
        self.times = []
        self.detunings = []
        self.start_time = time.time()
        self.max_history = 120  # seconds

        # Store f0 and update only when state selection changes
        self.f0 = None

        self.setup_layout()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(10)  # update every 10 ms

    def setup_layout(self):
        # Create main vertical layout
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        layout.addLayout(self.setup_state_selection())
        
        layout.addWidget(self.setup_wavemeter_display(), alignment=QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)

        layout.addWidget(self.setup_plot_widget())
        
        layout.addWidget(self.setup_avg_reading_display())
        
        layout.addLayout(self.setup_avg_N_spinner())
        layout.addWidget(self.setup_clear_button(), alignment=QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)

    def setup_plot_widget(self):
        # Plot widget
        self.plot_widget = pg.PlotWidget(title="Detuning vs Time")
        self.plot_widget.setLabel('left', 'Detuning', units='GHz')
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.curve = self.plot_widget.plot(pen='y')
        # Make y-axis numbers much bigger
        axis = self.plot_widget.getAxis('left')
        axis.setStyle(tickFont=pg.Qt.QtGui.QFont('Arial', 30))
        return self.plot_widget

    def setup_avg_reading_display(self):
        # Add a label for the average, aligned top right
        self.avg_label = QtWidgets.QLabel("Avg: --")
        self.avg_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        font = self.avg_label.font()
        font.setPointSize(36)
        font.setBold(True)
        self.avg_label.setFont(font)
        self.avg_label.setStyleSheet("color: rgba(255,100,100,1);")
        self.plot_widget.scene().sigMouseMoved.connect(lambda _: None)  # workaround for label overlay
        self.plot_widget.addItem(pg.TextItem(), ignoreBounds=True)  # force overlay
        return self.avg_label

    def setup_wavemeter_display(self):
        # Add a label for the wavemeter reading (THz), above the detuning label
        self.wavemeter_label = QtWidgets.QLabel("Wavemeter: -- THz")
        wavemeter_font = self.wavemeter_label.font()
        wavemeter_font.setPointSize(20)
        wavemeter_font.setBold(True)
        self.wavemeter_label.setFont(wavemeter_font)
        self.wavemeter_label.setAlignment(QtCore.Qt.AlignHCenter)
        self.wavemeter_label.setStyleSheet("color: #44aaff; margin-top: 10px;")
        return self.wavemeter_label

    def setup_clear_button(self):
        self.clear_button = QtWidgets.QPushButton("Clear/Reset")
        self.clear_button.setFixedHeight(50)
        self.clear_button.setStyleSheet("font-size: 24px;")
        self.clear_button.clicked.connect(self.clear_plot)
        return self.clear_button

    def setup_avg_N_spinner(self):
        n_layout = QtWidgets.QHBoxLayout()
        n_label = QtWidgets.QLabel("N points to average:")
        n_label.setStyleSheet("font-size: 16p;")
        self.n_spin = QtWidgets.QSpinBox()
        self.n_spin.setMinimum(10)
        self.n_spin.setMaximum(500)
        self.n_spin.setValue(100)
        self.n_spin.setFixedWidth(100)
        self.n_spin.setStyleSheet("font-size: 16px;")
        n_layout.addWidget(n_label)
        n_layout.addWidget(self.n_spin)
        n_layout.addStretch()
        return n_layout

    def setup_state_selection(self):
        self.l_to_L = {0: "S", 1: "P", 2: "D", 3: "F"}

        state_outer_layout = QtWidgets.QVBoxLayout()
        state_outer_layout.setAlignment(QtCore.Qt.AlignHCenter)

        state_grid = QtWidgets.QGridLayout()
        state_grid.setHorizontalSpacing(20)
        state_grid.setVerticalSpacing(10)

        label_init = QtWidgets.QLabel("Initial State")
        label_final = QtWidgets.QLabel("Final State")
        font_label = label_init.font()
        font_label.setPointSize(18)
        font_label.setBold(True)
        label_init.setFont(font_label)
        label_final.setFont(font_label)
        state_grid.addWidget(label_init, 1, 0, alignment=QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        state_grid.addWidget(label_final, 2, 0, alignment=QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        for col, lbl in enumerate(["n", "l", "j"]):
            lab = QtWidgets.QLabel(lbl)
            font = lab.font()
            font.setPointSize(16)
            font.setBold(False)
            lab.setFont(font)
            lab.setAlignment(QtCore.Qt.AlignHCenter)
            state_grid.addWidget(lab, 0, col + 1, alignment=QtCore.Qt.AlignHCenter)

        self.n0_spin = QtWidgets.QSpinBox()
        self.n0_spin.setRange(1, 10)
        self.n0_spin.setValue(4)
        state_grid.addWidget(self.n0_spin, 1, 1)

        self.l0_spin = QtWidgets.QSpinBox()
        self.l0_spin.setRange(0, 3)
        self.l0_spin.setValue(0)
        state_grid.addWidget(self.l0_spin, 1, 2)

        self.j0_combo = QtWidgets.QComboBox()
        self.j0_combo.addItems(["1/2", "3/2"])
        self.j0_combo.setCurrentIndex(0)
        state_grid.addWidget(self.j0_combo, 1, 3)

        self.state0_notation = QtWidgets.QLabel()
        font0 = self.state0_notation.font()
        font0.setPointSize(18)
        self.state0_notation.setFont(font0)
        state_grid.addWidget(self.state0_notation, 1, 4, alignment=QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.n1_spin = QtWidgets.QSpinBox()
        self.n1_spin.setRange(1, 10)
        self.n1_spin.setValue(4)
        state_grid.addWidget(self.n1_spin, 2, 1)

        self.l1_spin = QtWidgets.QSpinBox()
        self.l1_spin.setRange(0, 3)
        self.l1_spin.setValue(1)
        state_grid.addWidget(self.l1_spin, 2, 2)

        self.j1_combo = QtWidgets.QComboBox()
        self.j1_combo.addItems(["1/2", "3/2"])
        self.j1_combo.setCurrentIndex(0)
        state_grid.addWidget(self.j1_combo, 2, 3)

        self.state1_notation = QtWidgets.QLabel()
        font1 = self.state1_notation.font()
        font1.setPointSize(18)
        self.state1_notation.setFont(font1)
        state_grid.addWidget(self.state1_notation, 2, 4, alignment=QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        state_outer_layout.addLayout(state_grid)

        # Transition frequency label
        self.transition_freq_label = QtWidgets.QLabel()
        freq_font = self.transition_freq_label.font()
        freq_font.setPointSize(20)
        freq_font.setBold(True)
        self.transition_freq_label.setFont(freq_font)
        self.transition_freq_label.setAlignment(QtCore.Qt.AlignHCenter)
        self.transition_freq_label.setStyleSheet("color: #44aaff; margin-top: 10px;")

        def update_state_notation():
            n0 = self.n0_spin.value()
            l0 = self.l0_spin.value()
            j0 = self.j0_combo.currentText()
            L0 = self.l_to_L.get(l0, "?")
            self.state0_notation.setText(f"{n0}{L0}<sub>{j0}</sub>")
            n1 = self.n1_spin.value()
            l1 = self.l1_spin.value()
            j1 = self.j1_combo.currentText()
            L1 = self.l_to_L.get(l1, "?")
            self.state1_notation.setText(f"{n1}{L1}<sub>{j1}</sub>")
            update_transition_freq()

        def update_transition_freq():
            try:
                n0 = self.n0_spin.value()
                l0 = self.l0_spin.value()
                j0 = 1/2 if self.j0_combo.currentText() == "1/2" else 3/2
                n1 = self.n1_spin.value()
                l1 = self.l1_spin.value()
                j1 = 1/2 if self.j1_combo.currentText() == "1/2" else 3/2
                if (n0, l0, j0, n1, l1, j1) == (4,0,1/2,4,1,1/2):
                    freq_thz = 389.286305  # Hardcoded for the specific transition
                    extra_str = " (crossover to F'=2):\n"
                else:
                    freq_thz = self.atom.getTransitionFrequency(n0, l0, j0, n1, l1, j1) / 1e12
                    extra_str = "(ARC):\n"
                self.transition_freq_label.setText(f"Transition frequency{extra_str} {freq_thz:.6f} THz")
                self.f0 = freq_thz  # Store f0 in THz
            except Exception as e:
                self.transition_freq_label.setText("Transition frequency: --")
                self.f0 = None

        self.n0_spin.valueChanged.connect(update_state_notation)
        self.l0_spin.valueChanged.connect(update_state_notation)
        self.j0_combo.currentIndexChanged.connect(update_state_notation)
        self.n1_spin.valueChanged.connect(update_state_notation)
        self.l1_spin.valueChanged.connect(update_state_notation)
        self.j1_combo.currentIndexChanged.connect(update_state_notation)
        update_state_notation()

        state_outer_layout.addWidget(self.transition_freq_label)
        return state_outer_layout

    def get_detuning(self):
        try:
            freq = float(self.fzw.ask('MEAS,FREQ').split(' ')[0])
            if self.f0 is None:
                return np.nan
            detuning = (freq - self.f0) * 1.e3  # GHz
            return detuning
        except Exception as e:
            print("Error getting detuning:", e)
            return np.nan

    def update_plot(self):
        t = time.time() - self.start_time
        try:
            freq = float(self.fzw.ask('MEAS,FREQ').split(' ')[0])
            self.wavemeter_label.setText(f"Wavemeter: {freq:.6f} THz")
        except Exception:
            self.wavemeter_label.setText("Wavemeter: -- THz")
            freq = np.nan

        d = self.get_detuning()
        self.times.append(t)
        self.detunings.append(d)
        # Keep only the last 2 minutes of data
        while self.times and (t - self.times[0] > self.max_history):
            self.times.pop(0)
            self.detunings.pop(0)
        self.curve.setData(self.times, self.detunings)

        # Update average and std label
        N = self.n_spin.value()
        lastN = [x for x in self.detunings[-N:] if not np.isnan(x)]
        if lastN:
            avg = np.mean(lastN)
            std = np.std(lastN, ddof=1) if len(lastN) > 1 else 0.0
            self.avg_label.setText(f"Δ = {avg:.5f} GHz\nσ = {std*1.e3:.2f} MHz")
        else:
            self.avg_label.setText("Avg: --")

    def clear_plot(self):
        self.times = []
        self.detunings = []
        self.start_time = time.time()
        self.curve.clear()
        self.plot_widget.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.avg_label.setText("Avg: --")

def run_gui():
    # Use atom and fzw from the notebook
    atom = Potassium39()
    fzw = MOGDevice('192.168.1.94')

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = DetuningPlotter(atom, fzw)
    win.setWindowTitle("Live Detuning Plot")
    win.show()
    app.exec_()
    fzw.close()

# Run this cell to launch the GUI
run_gui()