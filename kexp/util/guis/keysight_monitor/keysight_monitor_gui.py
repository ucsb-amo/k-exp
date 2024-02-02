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
FONTSIZE_PT = 18

# one of these per current supply
class current_supply_widget(QWidget):
    def __init__(self,ip:str,max_current:int):
        super().__init__()
        self.ip = ip
        self.max_current = max_current
        self.supply = vxi11.Instrument(ip)

        self.init_UI()
        
    def read_current(self,supply):
        # send the supply the query to measure the current
        supply.write(":MEASure:CURRent:DC?")
        # wait a bit for the reply to be available (probably don't need this)
        time.sleep(0.05)
        # read out the value that the supply sends back -- convert it to a
        # number since it's a nasty string
        return float(supply.read())
    
    def update_current_UI(self):
        current = self.read_current(self.supply)
        # set the value text of our box (see "init_UI") to the new current
        # the "1.4f" formats the number to a string as with 4 decimal places (f for "float")
        self.value_label.setText(f"{current:1.4f}") 
    
    def init_UI(self):

        # this one gets "self" (is an attribute) since I'll need to update it
        # later when I check the current value
        self.value_label = QLabel("")
        self.value_label.setStyleSheet("font-weight: bold; font-size: {FONTSIZE_PT}pt")

        # these ones will remain the same forever so I just name them here and
        # don't bother to save them as an attribute (since I don't need to
        # reassign them later)
        text_label = QLabel(f"{self.max_current} A supply current = ")
        text_label.setStyleSheet("font-size: {FONTSIZE_PT}pt") # formatting

        unit_label = QLabel("A")
        unit_label.setStyleSheet("font-weight: bold; font-size: {FONTSIZE_PT}pt") # formatting

        # the overall layout of this part will have widgets in a horizontal line
        self.layout = QHBoxLayout() 
        # now I just stack the parts of this part of the GUI into the layout in order
        self.layout.addWidget(text_label)
        self.layout.addWidget(self.value_label)
        self.layout.addWidget(unit_label)

class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.init_instruments()
        self.setup_timer_loop()
        self.set_layout()

    def setup_timer_loop(self):
        # the window gets a timer object, this runs the "connected" function
        # each time that the timer times out (exceeds T_UPDATE_MS), then runs
        # again. effect is to run the "connected" function repeatedly every
        # T_UPDATE_MS (defined way at top of file)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_current)
        self.timer.start(T_UPDATE_MS)

    def init_instruments(self):
        current_supplies = [(170,"192.168.1.77"),
                            (500,"192.168.1.78")]
        self.supply_UIs = []
        for current, ip in current_supplies:
            self.supply_UIs.append(current_supply_widget(ip,current))

    def set_layout(self):
        self.layout = QVBoxLayout()
        # stack the layout for each of the supply UIs into the main window layout
        for supply_UI in self.supply_UIs:
            self.layout.addLayout(supply_UI.layout)

    def update_current(self):
        for supply_UI in self.supply_UIs:
            supply_UI.update_current_UI()
    
def main():
    app = QApplication(sys.argv)

    app.setStyle("Windows") # fun formatting

    window = Window()
    window.setLayout(window.layout)
    window.setWindowTitle("Keysight PSU Monitor")
    window.setWindowIcon(QIcon('banana-icon.png'))
    window.setFixedSize(400, 100)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()