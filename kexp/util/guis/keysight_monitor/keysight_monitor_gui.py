import numpy as np

import sys

from subprocess import PIPE, run
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox, QComboBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon

import vxi11
import time

T_UPDATE_MS = 250

class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.init_instruments()
        self.init_UI()
        self.set_layout()

    def init_instruments(self):
        self.supply_500A = vxi11.Instrument("192.168.1.78")
        self.supply_170A = vxi11.Instrument("192.168.1.77")

    def init_UI(self):

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_current)
        self.timer.start(T_UPDATE_MS)

        self.current_500A = QLabel("")
        self.current_500A.setStyleSheet("font-weight: bold; font-size: 18pt")
        self.current_500A_label = QLabel("500 A supply current = ")
        self.current_500A_label.setStyleSheet("font-size: 18pt")
        self.unit_500 = QLabel("A")
        self.unit_500.setStyleSheet("font-weight: bold; font-size: 18pt")

        self.current_170A = QLabel("")
        self.current_170A.setStyleSheet("font-weight: bold; font-size: 18pt")
        self.current_170A_label = QLabel("170 A supply current = ")
        self.current_170A_label.setStyleSheet("font-size: 18pt")
        self.unit_170 = QLabel("A")
        self.unit_170.setStyleSheet("font-weight: bold; font-size: 18pt")

    def set_layout(self):
        layout = QVBoxLayout()

        # title = QLabel("Keysight PSU Monitor")

        layout_500 = QHBoxLayout()
        layout_500.addWidget(self.current_500A_label)
        layout_500.addWidget(self.current_500A)
        layout_500.addWidget(self.unit_500)

        layout_170 = QHBoxLayout()
        layout_170.addWidget(self.current_170A_label)
        layout_170.addWidget(self.current_170A)
        layout_170.addWidget(self.unit_170)

        # self.layout.addWidget(title)
        layout.addLayout(layout_500)
        layout.addLayout(layout_170)

        self.layout = layout

    def update_current(self):
        I_500A = self.read_current(self.supply_500A)
        self.current_500A.setText(f"{I_500A:1.4f}")
        I_170A = self.read_current(self.supply_170A)
        self.current_170A.setText(f"{I_170A:1.4f}")

    def read_current(self,supply):
        supply.write(":MEASure:CURRent:DC?")
        time.sleep(0.05)
        return float(supply.read())
    
def main():
    app = QApplication(sys.argv)
    window = QWidget()

    app.setStyle("Windows")

    grid = Window()
    window.setLayout(grid.layout)
    window.setWindowTitle("Keysight PSU Monitor")
    window.setWindowIcon(QIcon('banana-icon.png'))

    window.setFixedSize(400, 100)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()